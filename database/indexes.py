from __future__ import annotations

import logging
from pymongo import ASCENDING
from config import COLLECTION_TO_OUTPUT_COMMAND
from database.mongo import get_db

log = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    """Create lightweight indexes. Safe to run repeatedly."""
    db = get_db()
    for collection in COLLECTION_TO_OUTPUT_COMMAND:
        col = db[collection]
        try:
            await col.create_index([("file_unique_id", ASCENDING)], background=True)
            await col.create_index([("sha256", ASCENDING)], background=True)
            await col.create_index([("phash", ASCENDING)], background=True)
            await col.create_index([("card_id", ASCENDING)], background=True)
            await col.create_index([("name", ASCENDING)], background=True)
            await col.create_index([("media_type", ASCENDING)], background=True)
        except Exception:
            log.exception("failed to ensure indexes for %s", collection)
    await db["settings"].create_index([("key", ASCENDING)], unique=True, background=True)
    await db["known_users"].create_index([("user_id", ASCENDING)], unique=True, background=True)
