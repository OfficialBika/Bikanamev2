from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

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
    anime_name: str | None = None
    media_type: str | None = None
    file_unique_id: str | None = None
    sha256: str | None = None
    phash: str | None = None
    frame_hashes: tuple[str, ...] = ()

    @property
    def is_waifux(self) -> bool:
        return self.collection == "items_waifux_grab"


def _nested(doc: dict, path: str):
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _first_present(doc: dict, names: Iterable[str]):
    for name in names:
        value = _nested(doc, name) if "." in name else doc.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def _clean(value) -> str | None:
    if value in (None, ""):
        return None
    try:
        s = str(value).strip()
    except Exception:
        return None
    return s or None


def _parse_frame_hashes(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, str):
        return tuple(x.strip() for x in value.split(",") if x.strip())
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for x in value:
            if isinstance(x, dict):
                x = x.get("hash") or x.get("phash") or x.get("value")
            if x:
                s = str(x).strip()
                if s:
                    out.append(s)
        return tuple(out)
    return ()


def _guess_media_type(doc: dict, phash: str | None, frame_hashes: tuple[str, ...]) -> str | None:
    raw = _first_present(doc, ["media_type", "type", "media.type", "file_type"])
    media_type = str(raw or "").lower().strip()
    if media_type in {"photo", "image", "pic", "picture"}:
        return "photo"
    if media_type in {"video", "animation", "gif"}:
        return "video"
    if frame_hashes:
        return "video"
    if phash:
        return "photo"
    return media_type or None


NAME_FIELDS = [
    "name", "character_name", "char_name", "item_name", "card_name", "display_name", "title",
    "media.name", "photo.name", "video.name", "character.name",
]
ANIME_FIELDS = ["anime_name", "anime", "series", "movie", "category", "media.series", "character.series"]
ID_FIELDS = ["card_id", "id", "item_id", "char_id", "character_id", "media.id", "character.id"]
RARITY_FIELDS = ["rarity", "rank", "tier", "class", "media.rarity", "character.rarity"]
FILE_UID_FIELDS = ["file_unique_id", "photo_file_unique_id", "video_file_unique_id", "media.file_unique_id", "file.unique_id"]
SHA_FIELDS = ["sha256", "media_sha256", "hash", "file_hash", "media.sha256", "file.sha256"]
PHASH_FIELDS = ["phash", "photo_phash", "image_phash", "media.phash", "file.phash"]
FRAME_HASH_FIELDS = ["frame_hashes", "video_frame_hashes", "frames", "media.frame_hashes", "file.frame_hashes"]


class SnapshotCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.loaded_at = 0.0
        self.count = 0
        self.by_collection: Dict[str, List[ItemSnapshot]] = {}
        self.file_uid: Dict[str, ItemSnapshot] = {}
        self.sha256: Dict[str, ItemSnapshot] = {}
        self.file_uid_by_collection: Dict[str, Dict[str, ItemSnapshot]] = {}
        self.sha256_by_collection: Dict[str, Dict[str, ItemSnapshot]] = {}
        self.photos_by_collection: Dict[str, List[ItemSnapshot]] = {}
        self.videos_by_collection: Dict[str, List[ItemSnapshot]] = {}

    async def refresh(self) -> None:
        db = get_db()
        new_by_collection: Dict[str, List[ItemSnapshot]] = {}
        new_file_uid: Dict[str, ItemSnapshot] = {}
        new_sha256: Dict[str, ItemSnapshot] = {}
        new_file_uid_by_col: Dict[str, Dict[str, ItemSnapshot]] = {}
        new_sha256_by_col: Dict[str, Dict[str, ItemSnapshot]] = {}
        new_photos: Dict[str, List[ItemSnapshot]] = {}
        new_videos: Dict[str, List[ItemSnapshot]] = {}

        projection = {field.split(".")[0]: 1 for field in set(NAME_FIELDS + ANIME_FIELDS + ID_FIELDS + RARITY_FIELDS + FILE_UID_FIELDS + SHA_FIELDS + PHASH_FIELDS + FRAME_HASH_FIELDS)}
        projection.update({"command_name": 1, "source_key": 1, "source_collection": 1})

        total = 0
        for collection, default_command in COLLECTION_TO_OUTPUT_COMMAND.items():
            docs: List[ItemSnapshot] = []
            try:
                cursor = db[collection].find({}, projection=projection, no_cursor_timeout=False)
                async for d in cursor:
                    name_raw = _first_present(d, NAME_FIELDS)
                    name = normalize_name(name_raw)
                    if not name:
                        continue
                    phash = _clean(_first_present(d, PHASH_FIELDS))
                    frame_hashes = _parse_frame_hashes(_first_present(d, FRAME_HASH_FIELDS))
                    media_type = _guess_media_type(d, phash, frame_hashes)
                    command = _clean(d.get("command_name")) or default_command
                    item = ItemSnapshot(
                        collection=collection,
                        command=command,
                        name=name,
                        card_id=_clean(_first_present(d, ID_FIELDS)),
                        rarity=_clean(_first_present(d, RARITY_FIELDS)),
                        anime_name=_clean(_first_present(d, ANIME_FIELDS)),
                        media_type=media_type,
                        file_unique_id=_clean(_first_present(d, FILE_UID_FIELDS)),
                        sha256=_clean(_first_present(d, SHA_FIELDS)),
                        phash=phash,
                        frame_hashes=frame_hashes,
                    )
                    docs.append(item)
                    total += 1

                    if item.file_unique_id:
                        new_file_uid.setdefault(item.file_unique_id, item)
                        new_file_uid_by_col.setdefault(collection, {})[item.file_unique_id] = item
                    if item.sha256:
                        new_sha256.setdefault(item.sha256, item)
                        new_sha256_by_col.setdefault(collection, {})[item.sha256] = item
                    if item.phash or media_type == "photo":
                        new_photos.setdefault(collection, []).append(item)
                    if item.frame_hashes or media_type == "video":
                        new_videos.setdefault(collection, []).append(item)
            except Exception:
                log.exception("snapshot load failed for %s", collection)
            new_by_collection[collection] = docs
            new_file_uid_by_col.setdefault(collection, {})
            new_sha256_by_col.setdefault(collection, {})
            new_photos.setdefault(collection, [])
            new_videos.setdefault(collection, [])

        async with self._lock:
            self.by_collection = new_by_collection
            self.file_uid = new_file_uid
            self.sha256 = new_sha256
            self.file_uid_by_collection = new_file_uid_by_col
            self.sha256_by_collection = new_sha256_by_col
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
