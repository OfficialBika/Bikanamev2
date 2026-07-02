from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Iterable

from aiogram import Bot
from aiogram.types import Message

from config import settings
from services.hash_service import MediaHash, hamming_hex, hash_photo, hash_video
from services.snapshot_cache import ItemSnapshot, snapshot
from services.source_resolver import output_command_from_message, resolve_lookup_scope, all_lookup_collections

# Optional hard block guard. If a blocked source reaches lookup_service,
# return blocked_source before any DB/cache/hash lookup.
try:
    from services.source_blocker import is_blocked_source  # type: ignore
except Exception:  # pragma: no cover
    def is_blocked_source(message: Message | None) -> bool:  # type: ignore
        return False
from utils.media import extract_media
from utils.perf import perf
from utils.ttl_cache import TTLCache

log = logging.getLogger(__name__)

CollectionFilter = list[str] | None


@dataclass(frozen=True)
class LookupResult:
    item: ItemSnapshot | None
    reason: str = ""
    elapsed_ms: float = 0.0


class LookupService:
    """Fast and accurate source-scoped lookup service.

    Behavior:
    - Auto lookup resolves source by bot/channel username/title/chat-id first.
    - If source is unknown, it reads command in forwarded caption/text and searches only
      the command collection(s), not the whole database.
    - Manual lookup prefers replied media source, then command-message scope as fallback.
    - file_unique_id is always the fastest path.
    - If UID misses, optional hash fallback searches only the resolved scope.
    - All-collection fallback is disabled by default.
    """

    def __init__(self) -> None:
        self.result_cache: TTLCache[str, ItemSnapshot] = TTLCache(
            settings.result_cache_max_items,
            settings.result_cache_ttl_seconds,
        )
        self.miss_cache: TTLCache[str, bool] = TTLCache(
            settings.result_cache_max_items,
            settings.miss_cache_ttl_seconds,
        )
        self.download_sem = asyncio.Semaphore(settings.max_concurrent_downloads)
        self.lookup_sem = asyncio.Semaphore(settings.max_concurrent_lookups)

    async def lookup_message(self, bot: Bot, message: Message, *, manual: bool = False) -> LookupResult:
        t0 = time.perf_counter()
        hit = False
        error = False
        try:
            async with self.lookup_sem:
                media = extract_media(message)
                if not media:
                    return self._done(None, "no_media", t0)

                source_message = media.source_message

                # Safety layer for blocked source bots/channels.
                # Auto/manual handlers should catch this before lookup, but keep this here
                # so direct service calls can never search a blocked source.
                if is_blocked_source(source_message):
                    return self._done(None, "blocked_source", t0)

                scope = resolve_lookup_scope(source_message)
                if getattr(scope, "mode", "") == "blocked":
                    return self._done(None, "blocked_source", t0)

                if manual and is_blocked_source(message):
                    return self._done(None, "blocked_source", t0)

                # Manual command is often a reply to media. Prefer the media/forward source.
                # If the media has no source/cmd, use the command message itself (/bika, /pick, /loot).
                if manual and not scope.collections:
                    manual_scope = resolve_lookup_scope(message)
                    if manual_scope.collections:
                        scope = manual_scope

                collection_filter = scope.collections
                filter_tag = self._filter_tag(collection_filter)

                if self._setting_bool("require_lookup_scope", True) and not collection_filter:
                    return self._done(None, "no_scope", t0)

                output_command = output_command_from_message(
                    source_message,
                    collection_filter[0] if collection_filter and len(collection_filter) == 1 else None,
                )
                if manual and not output_command:
                    output_command = output_command_from_message(
                        message,
                        collection_filter[0] if collection_filter and len(collection_filter) == 1 else None,
                    )

                file_uid = getattr(media.obj, "file_unique_id", None) or ""

                # 1) Exact UID lookup inside resolved source/command scope.
                if file_uid:
                    item = self._lookup_uid(file_uid, collection_filter)
                    if item:
                        hit = True
                        return self._done(self._with_command(item, output_command), "uid", t0)

                    miss_uid_key = f"uid:{filter_tag}:{file_uid}"
                    if self.miss_cache.get(miss_uid_key):
                        # Miss cache means this exact scope+uid was already checked recently.
                        # If strict exact mode is OFF and hash fallback is ON, still skip only when hash miss was cached too.
                        if self._setting_bool("strict_exact_lookup_only", False) or not self._setting_bool("enable_hash_fallback", True):
                            return self._done(None, "miss_cache_uid", t0)

                    if collection_filter and self._setting_bool("strict_exact_lookup_only", False):
                        self.miss_cache.set(miss_uid_key, True)
                        return self._done(None, "not_found_source_uid", t0)
                else:
                    if self._setting_bool("strict_exact_lookup_only", False):
                        return self._done(None, "no_file_unique_id", t0)

                # 2) Optional source-scoped hash fallback for old DB/media where UID misses.
                if not self._setting_bool("enable_hash_fallback", True):
                    if file_uid:
                        self.miss_cache.set(f"uid:{filter_tag}:{file_uid}", True)
                    return self._done(None, "not_found_no_hash_fallback", t0)

                data = await self._download(bot, getattr(media.obj, "file_id", ""))
                if not data:
                    if file_uid:
                        self.miss_cache.set(f"uid:{filter_tag}:{file_uid}", True)
                    return self._done(None, "download_failed", t0)

                mh = await asyncio.to_thread(hash_photo if media.media_type == "photo" else hash_video, data)
                cache_key = f"sha:{mh.sha256}" if mh.sha256 else (f"uid:{file_uid}" if file_uid else "")
                miss_key = f"{cache_key}:{filter_tag}" if cache_key else ""

                if cache_key:
                    cached = self.result_cache.get(f"{cache_key}:{filter_tag}") or self.result_cache.get(cache_key)
                    if cached and self._matches_filter(cached.collection, collection_filter):
                        hit = True
                        return self._done(self._with_command(cached, output_command), "cache", t0)
                    if miss_key and self.miss_cache.get(miss_key):
                        return self._done(None, "miss_cache", t0)

                item = self._match_hash(mh, media.media_type, collection_filter)
                if item:
                    hit = True
                    if cache_key:
                        self.result_cache.set(f"{cache_key}:{filter_tag}", item)
                        self.result_cache.set(cache_key, item)
                    if file_uid:
                        self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
                        self.result_cache.set(f"uid:{file_uid}", item)
                    output_command = output_command_from_message(source_message, item.collection) or output_command
                    return self._done(self._with_command(item, output_command), "hash", t0)

                # 3) Compatibility fallback to all DB is explicitly disabled by default.
                if collection_filter and self._setting_bool("fallback_all_on_strict_miss", False):
                    fallback_item = self._lookup_uid(file_uid, None) if file_uid else None
                    if not fallback_item:
                        fallback_item = self._match_hash(mh, media.media_type, None)
                    if fallback_item:
                        hit = True
                        fallback_command = output_command_from_message(source_message, fallback_item.collection) or output_command
                        return self._done(
                            self._with_command(fallback_item, fallback_command),
                            f"{scope.mode}_fallback_hash",
                            t0,
                        )

                if miss_key:
                    self.miss_cache.set(miss_key, True)
                if file_uid:
                    self.miss_cache.set(f"uid:{filter_tag}:{file_uid}", True)
                return self._done(None, "not_found", t0)
        except Exception:
            error = True
            log.exception("lookup failed")
            return self._done(None, "error", t0)
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            perf.lookup.record(elapsed, hit=hit, error=error)

    def _setting_bool(self, name: str, default: bool) -> bool:
        env_val = os.getenv(name.upper())
        if env_val is not None:
            return env_val.strip().lower() in {"1", "true", "yes", "y", "on"}
        for key in (name, name.lower(), name.upper()):
            if hasattr(settings, key):
                return bool(getattr(settings, key))
        return default

    def _with_command(self, item: ItemSnapshot | None, output_command: str | None) -> ItemSnapshot | None:
        if not item or not output_command or item.command == output_command:
            return item
        return replace(item, command=output_command)

    def _done(self, item: ItemSnapshot | None, reason: str, t0: float) -> LookupResult:
        return LookupResult(item=item, reason=reason, elapsed_ms=(time.perf_counter() - t0) * 1000)

    def _filter_tag(self, collection_filter: CollectionFilter) -> str:
        return "+".join(collection_filter) if collection_filter else "all"

    def _matches_filter(self, collection: str, collection_filter: CollectionFilter) -> bool:
        return not collection_filter or collection in collection_filter

    def _lookup_uid(self, file_uid: str, collection_filter: CollectionFilter) -> ItemSnapshot | None:
        if not file_uid:
            return None
        filter_tag = self._filter_tag(collection_filter)

        cached = self.result_cache.get(f"uid:{filter_tag}:{file_uid}")
        if cached and self._matches_filter(cached.collection, collection_filter):
            return cached

        cached = self.result_cache.get(f"uid:{file_uid}")
        if cached and self._matches_filter(cached.collection, collection_filter):
            self.result_cache.set(f"uid:{filter_tag}:{file_uid}", cached)
            return cached

        # O(1) per-collection maps from improved snapshot_cache.py.
        by_col = getattr(snapshot, "file_uid_by_collection", None)
        if by_col and collection_filter:
            for collection in collection_filter:
                item = by_col.get(collection, {}).get(file_uid)
                if item:
                    self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
                    self.result_cache.set(f"uid:{file_uid}", item)
                    return item

        # Backward-compatible scoped scan if snapshot_cache.py is old.
        if collection_filter:
            for collection in collection_filter:
                for item in getattr(snapshot, "by_collection", {}).get(collection, []):
                    if item.file_unique_id == file_uid:
                        self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
                        self.result_cache.set(f"uid:{file_uid}", item)
                        return item
            return None

        item = snapshot.file_uid.get(file_uid)
        if item:
            self.result_cache.set(f"uid:{file_uid}", item)
            return item
        return None

    async def _download(self, bot: Bot, file_id: str) -> bytes | None:
        if not file_id:
            return None
        async with self.download_sem:
            try:
                bio = await asyncio.wait_for(bot.download(file_id), timeout=settings.download_timeout_seconds)
                if isinstance(bio, io.BytesIO):
                    return bio.getvalue()
                if hasattr(bio, "read"):
                    return bio.read()
                return None
            except asyncio.TimeoutError:
                log.info("download timeout after %ss", settings.download_timeout_seconds)
                return None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.info("download failed: %s", exc)
                return None

    def _candidate_collections(self, collection_filter: CollectionFilter) -> Iterable[str]:
        return collection_filter or all_lookup_collections()

    def _candidates(self, collection_filter: CollectionFilter, media_type: str) -> list[ItemSnapshot]:
        source = snapshot.photos_by_collection if media_type == "photo" else snapshot.videos_by_collection
        out: list[ItemSnapshot] = []
        for collection in self._candidate_collections(collection_filter):
            out.extend(source.get(collection, []))
        return out

    def _lookup_sha256(self, sha256: str, collection_filter: CollectionFilter) -> ItemSnapshot | None:
        if not sha256:
            return None
        by_col = getattr(snapshot, "sha256_by_collection", None)
        if by_col and collection_filter:
            for collection in collection_filter:
                item = by_col.get(collection, {}).get(sha256)
                if item:
                    return item
        if collection_filter:
            for item in self._candidates(collection_filter, "photo") + self._candidates(collection_filter, "video"):
                if item.sha256 == sha256:
                    return item
            return None
        return snapshot.sha256.get(sha256)

    def _match_hash(self, mh: MediaHash, media_type: str, collection_filter: CollectionFilter) -> ItemSnapshot | None:
        if mh.sha256:
            exact = self._lookup_sha256(mh.sha256, collection_filter)
            if exact:
                return exact

        best: tuple[float, ItemSnapshot] | None = None
        for item in self._candidates(collection_filter, media_type):
            is_waifux = item.collection == "items_waifux_grab"
            if media_type == "photo" and mh.phash and item.phash:
                d = hamming_hex(mh.phash, item.phash)
                threshold = (
                    getattr(settings, "waifux_photo_phash_threshold", settings.photo_phash_threshold)
                    if is_waifux else settings.photo_phash_threshold
                )
                if d is not None and d <= threshold and (best is None or d < best[0]):
                    best = (float(d), item)
            elif media_type == "video" and mh.frame_hashes and item.frame_hashes:
                ds: list[int] = []
                for a, b in zip(mh.frame_hashes, item.frame_hashes):
                    d = hamming_hex(a, b)
                    if d is not None:
                        ds.append(d)
                if not ds:
                    continue
                avg = sum(ds) / len(ds)
                frame_threshold = (
                    getattr(settings, "waifux_video_frame_threshold", settings.video_frame_threshold)
                    if is_waifux else settings.video_frame_threshold
                )
                avg_threshold = (
                    getattr(settings, "waifux_video_avg_threshold", settings.video_avg_threshold)
                    if is_waifux else settings.video_avg_threshold
                )
                if min(ds) <= frame_threshold and avg <= avg_threshold:
                    if best is None or avg < best[0]:
                        best = (avg, item)
        return best[1] if best else None


lookup_service = LookupService()
