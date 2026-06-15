from __future__ import annotations

import asyncio
import io
import logging
import time
from dataclasses import dataclass, replace
from typing import Iterable

from aiogram import Bot
from aiogram.types import Message

from config import settings
from services.hash_service import MediaHash, hamming_hex, hash_photo, hash_video
from services.snapshot_cache import ItemSnapshot, snapshot
from services.source_resolver import output_command_from_message, resolve_lookup_collections, resolve_lookup_scope, all_lookup_collections
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
    def __init__(self) -> None:
        self.result_cache: TTLCache[str, ItemSnapshot] = TTLCache(settings.result_cache_max_items, settings.result_cache_ttl_seconds)
        self.miss_cache: TTLCache[str, bool] = TTLCache(settings.result_cache_max_items, settings.miss_cache_ttl_seconds)
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

                # Fast scoped lookup:
                # 1) source/forward collection, 2) command collection group, 3) all collections.
                # If a scoped search misses, settings.fallback_all_on_strict_miss controls
                # whether we do the old all-database fallback.
                scope = resolve_lookup_scope(source_message)
                collection_filter = scope.collections
                output_command = output_command_from_message(
                    source_message,
                    collection_filter[0] if collection_filter and len(collection_filter) == 1 else None,
                )

                # Strict source mode:
                # If the media has no trusted source/command scope, do NOT search all collections.
                # This prevents wrong-source matches and also avoids expensive download/hash work.
                if settings.require_lookup_scope and not collection_filter:
                    return self._done(None, "scope_missing", t0)

                file_uid = getattr(media.obj, "file_unique_id", None)
                filter_tag = self._filter_tag(collection_filter)

                if file_uid:
                    item = self._lookup_uid(file_uid, collection_filter)
                    if item:
                        hit = True
                        return self._done(self._with_command(item, output_command), "uid", t0)
                    if self.miss_cache.get(f"uid:{filter_tag}:{file_uid}"):
                        # If fallback is enabled, do not stop on a scoped UID miss.
                        # The same media may still be found by hash in another collection.
                        if not (collection_filter and settings.fallback_all_on_strict_miss):
                            return self._done(None, "miss_cache_uid", t0)

                data = await self._download(bot, getattr(media.obj, "file_id"))
                if not data:
                    return self._done(None, "download_failed", t0)

                mh = await asyncio.to_thread(hash_photo if media.media_type == "photo" else hash_video, data)
                cache_key = f"sha:{filter_tag}:{mh.sha256}" if mh.sha256 else (f"uid:{filter_tag}:{file_uid}" if file_uid else "")
                miss_key = f"{cache_key}:{filter_tag}" if cache_key else ""

                if cache_key:
                    cached = self.result_cache.get(cache_key)
                    if cached and self._matches_filter(cached.collection, collection_filter):
                        hit = True
                        return self._done(self._with_command(cached, output_command), "cache", t0)
                    if miss_key and self.miss_cache.get(miss_key):
                        if not (collection_filter and settings.fallback_all_on_strict_miss):
                            return self._done(None, "miss_cache", t0)

                item = self._match_hash(mh, media.media_type, collection_filter)
                if item:
                    hit = True
                    if cache_key:
                        self.result_cache.set(cache_key, item)
                    if file_uid:
                        self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
                    output_command = output_command_from_message(source_message, item.collection) or output_command
                    return self._done(self._with_command(item, output_command), "hash", t0)

                # Strict mode: no all-collection fallback. If the resolved source/command
                # scope misses, return Not Found immediately.
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

    def _with_command(self, item: ItemSnapshot | None, output_command: str | None) -> ItemSnapshot | None:
        if not item or not output_command or item.command == output_command:
            return item
        return replace(item, command=output_command)

    def _done(self, item: ItemSnapshot | None, reason: str, t0: float) -> LookupResult:
        return LookupResult(item=item, reason=reason, elapsed_ms=(time.perf_counter() - t0) * 1000)

    def _filter_tag(self, collection_filter: CollectionFilter) -> str:
        if not collection_filter:
            return "all"
        return "+".join(collection_filter)

    def _matches_filter(self, collection: str, collection_filter: CollectionFilter) -> bool:
        return not collection_filter or collection in collection_filter

    def _lookup_uid(self, file_uid: str, collection_filter: CollectionFilter) -> ItemSnapshot | None:
        filter_tag = self._filter_tag(collection_filter)
        cached = self.result_cache.get(f"uid:{filter_tag}:{file_uid}") or self.result_cache.get(f"uid:{file_uid}")
        if cached and self._matches_filter(cached.collection, collection_filter):
            return cached

        if collection_filter:
            for collection in collection_filter:
                item = snapshot.file_uid_by_collection.get(collection, {}).get(file_uid)
                if item:
                    self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
                    return item
            return None

        item = snapshot.file_uid.get(file_uid)
        if item:
            self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
            self.result_cache.set(f"uid:{filter_tag}:{file_uid}", item)
            return item
        return None

    async def _download(self, bot: Bot, file_id: str) -> bytes | None:
        async with self.download_sem:
            try:
                bio = await asyncio.wait_for(bot.download(file_id), timeout=settings.download_timeout_seconds)
                if isinstance(bio, io.BytesIO):
                    return bio.getvalue()
                if hasattr(bio, "read"):
                    return bio.read()
                return None
            except Exception:
                log.warning("download failed", exc_info=True)
                return None

    def _candidate_collections(self, collection_filter: CollectionFilter) -> Iterable[str]:
        if collection_filter:
            return collection_filter
        return all_lookup_collections()

    def _candidates(self, collection_filter: CollectionFilter, media_type: str) -> list[ItemSnapshot]:
        source = snapshot.photos_by_collection if media_type == "photo" else snapshot.videos_by_collection
        out: list[ItemSnapshot] = []
        for collection in self._candidate_collections(collection_filter):
            out.extend(source.get(collection, []))
        return out

    def _match_hash(self, mh: MediaHash, media_type: str, collection_filter: CollectionFilter) -> ItemSnapshot | None:
        if mh.sha256:
            if collection_filter:
                for collection in collection_filter:
                    exact = snapshot.sha256_by_collection.get(collection, {}).get(mh.sha256)
                    if exact:
                        return exact
            else:
                exact = snapshot.sha256.get(mh.sha256)
                if exact:
                    return exact

            # Fallback inside the already-resolved source/command candidate list only.
            for item in self._candidates(collection_filter, media_type):
                if item.sha256 and item.sha256 == mh.sha256:
                    return item

        best: tuple[float, ItemSnapshot] | None = None
        for item in self._candidates(collection_filter, media_type):
            if media_type == "photo" and mh.phash and item.phash:
                d = hamming_hex(mh.phash, item.phash)
                if d is not None and d <= settings.photo_phash_threshold and (best is None or d < best[0]):
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
                if min(ds) <= settings.video_frame_threshold and avg <= settings.video_avg_threshold:
                    if best is None or avg < best[0]:
                        best = (avg, item)
        return best[1] if best else None


lookup_service = LookupService()
