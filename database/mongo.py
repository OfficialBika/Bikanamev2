from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import settings

log = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_mongo() -> AsyncIOMotorDatabase:
    global _client, _db

    if _client is not None and _db is not None:
        return _db

    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is missing")

    _client = AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=30000,
        socketTimeoutMS=120000,
        maxIdleTimeMS=120000,
        retryWrites=True,
    )

    _db = _client[settings.db_name]
    await _db.command("ping")

    log.info(
        "Mongo connected: db=%s timeout socket=120000ms connect=30000ms",
        settings.db_name,
    )
    return _db


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB is not initialized. Call init_mongo() first.")
    return _db


async def close_mongo() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None
