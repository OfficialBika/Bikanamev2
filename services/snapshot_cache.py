from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict

from config import COLLECTION_TO_OUTPUT_COMMAND, settings
from database.mongo import get_db
from utils.text import normalize_name

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemSnapshot:
    """Minimal lookup record kept in RAM.

    Deliberately contains ONLY:
      - collection/source
      - output command
      - name
      - Telegram file_unique_id values

    No id, rarity, anime, hashes, file_id, media metadata, or Mongo document
    is copied into the RAM snapshot.
    """
    collection: str
    command: str
    name: str
    file_unique_ids: tuple[str, ...] = ()

    @property
    def file_unique_id(self) -> str | None:
        return self.file_unique_ids[0] if self.file_unique_ids else None


def _uid_values(doc: dict) -> tuple[str, ...]:
    values: list[str] = []

    def add(value) -> None:
        if isinstance(value, (list, tuple, set)):
            for x in value:
                add(x)
            return
        if value in (None, ""):
            return
        value = str(value).strip()
        if value and value not in values:
            values.append(value)

    # Read every known Telegram UID representation. This is important because
    # older records may have only the scalar field while newer records keep all
    # photo-size/variant UIDs in file_unique_ids.
    add(doc.get("file_unique_ids"))
    add(doc.get("telegram_file_unique_id"))
    add(doc.get("file_unique_id"))
    add(doc.get("photo_file_unique_id"))
    add(doc.get("video_file_unique_id"))
    add((doc.get("media") or {}).get("file_unique_id") if isinstance(doc.get("media"), dict) else None)
    return tuple(values)


class SnapshotCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.loaded_at = 0.0
        self.count = 0

        # Only minimal records are retained.
        self.by_collection: Dict[str, tuple[ItemSnapshot, ...]] = {}
        self.file_uid_by_collection: Dict[str, Dict[str, ItemSnapshot]] = {}

        # Global UID keeps ALL exact matches instead of silently overwriting
        # duplicate UIDs from different sources.
        self.file_uid: Dict[str, tuple[ItemSnapshot, ...]] = {}

    async def refresh(self) -> None:
        db = get_db()
        new_by_collection: Dict[str, tuple[ItemSnapshot, ...]] = {}
        new_by_col: Dict[str, Dict[str, ItemSnapshot]] = {}
        global_lists: Dict[str, list[ItemSnapshot]] = {}

        # Mongo sends only name + command + UID fields.
        projection = {
            "_id": 0,
            "name": 1,
            "command_name": 1,
            "file_unique_id": 1,
            "telegram_file_unique_id": 1,
            "file_unique_ids": 1,
            "photo_file_unique_id": 1,
            "video_file_unique_id": 1,
            "media.file_unique_id": 1,
        }

        total = 0
        uid_count = 0

        for collection, default_command in COLLECTION_TO_OUTPUT_COMMAND.items():
            items: list[ItemSnapshot] = []
            try:
                cursor = db[collection].find({}, projection=projection)
                async for d in cursor:
                    name = normalize_name(d.get("name"))
                    if not name:
                        continue

                    uids = _uid_values(d)
                    if not uids:
                        # A lookup record without Telegram UID is useless for
                        # the exact fast path, so do not put it into RAM.
                        continue

                    command = str(d.get("command_name") or default_command).strip() or default_command
                    item = ItemSnapshot(
                        collection=collection,
                        command=command,
                        name=name,
                        file_unique_ids=uids,
                    )
                    items.append(item)
                    total += 1

                    scoped = new_by_col.setdefault(collection, {})
                    for uid in uids:
                        scoped.setdefault(uid, item)
                        global_lists.setdefault(uid, []).append(item)
                        uid_count += 1

            except Exception:
                log.exception("snapshot load failed for %s", collection)

            new_by_collection[collection] = tuple(items)
            new_by_col.setdefault(collection, {})

        # Freeze global values and de-duplicate the same collection/name record.
        new_global: Dict[str, tuple[ItemSnapshot, ...]] = {}
        for uid, candidates in global_lists.items():
            seen: set[tuple[str, str]] = set()
            unique: list[ItemSnapshot] = []
            for item in candidates:
                key = (item.collection, item.name)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
            new_global[uid] = tuple(unique)

        async with self._lock:
            self.by_collection = new_by_collection
            self.file_uid_by_collection = new_by_col
            self.file_uid = new_global
            self.loaded_at = time.time()
            self.count = total

        log.info(
            "minimal UID snapshot refreshed: records=%s unique_uids=%s uid_entries=%s",
            total,
            len(new_global),
            uid_count,
        )

    async def refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(max(10, settings.snapshot_refresh_seconds))
            try:
                await self.refresh()
            except Exception:
                log.exception("snapshot refresh loop failed")

    def age_seconds(self) -> int:
        return int(time.time() - self.loaded_at) if self.loaded_at else -1


snapshot = SnapshotCache()
