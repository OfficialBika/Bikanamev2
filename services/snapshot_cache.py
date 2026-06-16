from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List

from config import COLLECTION_TO_OUTPUT_COMMAND, settings
from database.mongo import get_db
from utils.text import normalize_name

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItemSnapshot:
    collection: str
    command: str
    name: str
    card_id: str | int | None = None
    rarity: str | None = None
    media_type: str | None = None
    file_unique_id: str | None = None
    sha256: str | None = None
    phash: str | None = None
    frame_hashes: tuple[str, ...] = ()

    @property
    def is_waifux(self) -> bool:
        return self.collection == "items_waifux_grab"


def _first_present(doc: dict, names: Iterable[str]):
    for name in names:
        value = doc.get(name)
        if value not in (None, ""):
            return value
    return None


def _parse_frame_hashes(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, str):
        return tuple(x.strip() for x in value.split(",") if x.strip())
    if isinstance(value, (list, tuple)):
        out = []
        for x in value:
            if isinstance(x, dict):
                x = x.get("hash") or x.get("phash")
            if x:
                out.append(str(x).strip())
        return tuple(x for x in out if x)
    return ()


class SnapshotCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.loaded_at = 0.0
        self.count = 0
        self.by_collection: Dict[str, List[ItemSnapshot]] = {}
        self.file_uid: Dict[str, ItemSnapshot] = {}
        self.sha256: Dict[str, ItemSnapshot] = {}
        self.photos_by_collection: Dict[str, List[ItemSnapshot]] = {}
        self.videos_by_collection: Dict[str, List[ItemSnapshot]] = {}

    async def refresh(self) -> None:
        db = get_db()
        new_by_collection: Dict[str, List[ItemSnapshot]] = {}
        new_file_uid: Dict[str, ItemSnapshot] = {}
        new_sha256: Dict[str, ItemSnapshot] = {}
        new_photos: Dict[str, List[ItemSnapshot]] = {}
        new_videos: Dict[str, List[ItemSnapshot]] = {}
        projection = {
            "name": 1, "character_name": 1, "card_id": 1, "id": 1, "rarity": 1,
            "media_type": 1, "type": 1, "file_unique_id": 1, "photo_file_unique_id": 1,
            "video_file_unique_id": 1, "sha256": 1, "media_sha256": 1, "hash": 1,
            "phash": 1, "photo_phash": 1, "frame_hashes": 1, "video_frame_hashes": 1,
        }
        total = 0
        for collection, command in COLLECTION_TO_OUTPUT_COMMAND.items():
            docs: List[ItemSnapshot] = []
            try:
                cursor = db[collection].find({}, projection=projection, no_cursor_timeout=False)
                async for d in cursor:
                    name = normalize_name(_first_present(d, ["name", "character_name"]))
                    if not name:
                        continue
                    media_type = str(_first_present(d, ["media_type", "type"]) or "").lower() or None
                    frame_hashes = _parse_frame_hashes(_first_present(d, ["frame_hashes", "video_frame_hashes"]))
                    item = ItemSnapshot(
                        collection=collection,
                        command=command,
                        name=name,
                        card_id=_first_present(d, ["card_id", "id"]),
                        rarity=None if collection == "items_waifux_grab" else _first_present(d, ["rarity"]),
                        media_type=media_type,
                        file_unique_id=_first_present(d, ["file_unique_id", "photo_file_unique_id", "video_file_unique_id"]),
                        sha256=_first_present(d, ["sha256", "media_sha256", "hash"]),
                        phash=_first_present(d, ["phash", "photo_phash"]),
                        frame_hashes=frame_hashes,
                    )
                    docs.append(item)
                    total += 1
                    if item.file_unique_id:
                        new_file_uid[item.file_unique_id] = item
                    if item.sha256:
                        new_sha256[item.sha256] = item
                    if item.phash or media_type == "photo":
                        new_photos.setdefault(collection, []).append(item)
                    if item.frame_hashes or media_type == "video":
                        new_videos.setdefault(collection, []).append(item)
            except Exception:
                log.exception("snapshot load failed for %s", collection)
            new_by_collection[collection] = docs

        async with self._lock:
            self.by_collection = new_by_collection
            self.file_uid = new_file_uid
            self.sha256 = new_sha256
            self.photos_by_collection = new_photos
            self.videos_by_collection = new_videos
            self.loaded_at = time.time()
            self.count = total
        log.info("snapshot refreshed: %s items", total)

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
