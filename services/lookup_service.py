from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, replace

from aiogram import Bot
from aiogram.types import Message

from config import settings
from services.snapshot_cache import ItemSnapshot, snapshot
from services.source_resolver import output_command_from_message, resolve_lookup_scope

try:
    from services.source_blocker import is_blocked_source  # type: ignore
except Exception:
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
    """Exact Telegram UID lookup.

    The hot path is intentionally tiny:
      1. resolve source scope
      2. read Telegram file_unique_id
      3. result-cache lookup
      4. O(1) RAM UID lookup
      5. manual-only global UID fallback when source is unknown

    There is NO miss-cache and NO media download/hash work in this service.
    """

    def __init__(self) -> None:
        self.result_cache: TTLCache[str, ItemSnapshot] = TTLCache(
            settings.result_cache_max_items,
            settings.result_cache_ttl_seconds,
        )
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

                if is_blocked_source(source_message):
                    return self._done(None, "blocked_source", t0)
                if manual and is_blocked_source(message):
                    return self._done(None, "blocked_source", t0)

                scope = resolve_lookup_scope(source_message)
                if getattr(scope, "mode", "") == "blocked":
                    return self._done(None, "blocked_source", t0)

                collections = list(scope.collections or [])

                # Manual commands such as /w or .w are often sent as a reply
                # to media. If the media itself has no source, try the command
                # message as the source hint.
                if manual and not collections:
                    manual_scope = resolve_lookup_scope(message)
                    if manual_scope.collections:
                        collections = list(manual_scope.collections)

                file_uid = str(getattr(media.obj, "file_unique_id", "") or "").strip()
                if not file_uid:
                    return self._done(None, "no_file_unique_id", t0)

                output_command = output_command_from_message(
                    source_message,
                    collections[0] if len(collections) == 1 else None,
                )
                if manual and not output_command:
                    output_command = output_command_from_message(
                        message,
                        collections[0] if len(collections) == 1 else None,
                    )

                filter_tag = "+".join(collections) if collections else "global"
                cache_key = f"uid:{filter_tag}:{file_uid}"

                # Result cache ONLY. A failed lookup is never cached.
                # Auto lookup may read cache only inside a resolved source scope.
                # Manual lookup may read an unambiguous global UID cache.
                cached = self.result_cache.get(cache_key)
                cached_is_current = bool(
                    cached
                    and (
                        (collections and cached.collection in collections)
                        or (
                            manual
                            and not collections
                            and any(
                                x.collection == cached.collection and x.name == cached.name
                                for x in snapshot.file_uid.get(file_uid, ())
                            )
                        )
                    )
                )
                if cached and cached_is_current:
                    hit = True
                    return self._done(self._with_command(cached, output_command), "cache", t0)

                # Source-aware exact UID lookup. Auto lookup is NEVER
                # allowed to turn an unknown source into a global search.
                item = self._lookup_uid(file_uid, collections)
                if item:
                    hit = True
                    self.result_cache.set(cache_key, item)
                    # Also keep a global result-cache entry only for an
                    # unambiguous exact UID.
                    if not collections:
                        self.result_cache.set(f"uid:global:{file_uid}", item)
                    return self._done(self._with_command(item, output_command), "uid", t0)

                # IMPORTANT: only manual lookup is allowed to use global UID
                # fallback when the source cannot be resolved. Auto lookup
                # remains source-scoped and never becomes a global search.
                if manual and not collections:
                    global_item = self._lookup_global_uid(file_uid)
                    if global_item:
                        hit = True
                        self.result_cache.set(cache_key, global_item)
                        return self._done(
                            self._with_command(
                                global_item,
                                output_command or global_item.command,
                            ),
                            "global_uid",
                            t0,
                        )

                return self._done(
                    None,
                    "not_found_global_uid" if manual and not collections else "not_found_source_uid",
                    t0,
                )

        except Exception:
            error = True
            log.exception("lookup failed")
            return self._done(None, "error", t0)
        finally:
            perf.lookup.record(
                (time.perf_counter() - t0) * 1000,
                hit=hit,
                error=error,
            )

    def _with_command(self, item: ItemSnapshot | None, output_command: str | None) -> ItemSnapshot | None:
        if not item or not output_command or item.command == output_command:
            return item
        return replace(item, command=output_command)

    def _done(self, item: ItemSnapshot | None, reason: str, t0: float) -> LookupResult:
        return LookupResult(
            item=item,
            reason=reason,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    def _lookup_uid(
        self,
        file_uid: str,
        collection_filter: CollectionFilter,
    ) -> ItemSnapshot | None:
        if not file_uid:
            return None

        if collection_filter:
            by_col = snapshot.file_uid_by_collection
            for collection in collection_filter:
                candidates = by_col.get(collection, {}).get(file_uid, ())
                if len(candidates) == 1:
                    return candidates[0]
                if len(candidates) > 1:
                    names = {x.name for x in candidates}
                    if len(names) == 1:
                        return candidates[0]
                    log.warning(
                        "ambiguous scoped UID: collection=%s uid=%s candidates=%s",
                        collection,
                        file_uid,
                        len(candidates),
                    )
            return None

        # Unknown source: do not allow auto lookup to search globally.
        # Manual lookup performs its explicit global fallback in lookup_message().
        return None

    def _lookup_global_uid(self, file_uid: str) -> ItemSnapshot | None:
        candidates = snapshot.file_uid.get(file_uid, ())
        if len(candidates) == 1:
            return candidates[0]

        # Never return an arbitrary record when the exact UID exists in
        # multiple sources. That would be a false positive.
        if len(candidates) > 1:
            log.warning(
                "ambiguous global UID: uid=%s candidates=%s",
                file_uid,
                len(candidates),
            )
        return None

    def _setting_bool(self, name: str, default: bool = False) -> bool:
        env_val = os.getenv(name.upper())
        if env_val is not None:
            return env_val.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(getattr(settings, name, default))


lookup_service = LookupService()
