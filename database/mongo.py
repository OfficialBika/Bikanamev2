from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_mongo() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is not None:
        return _db
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is empty")
    _client = AsyncIOMotorClient(
        settings.mongo_uri,
        maxPoolSize=80,
        minPoolSize=5,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=20000,
        retryWrites=True,
    )
    _db = _client[settings.db_name]
    await _client.admin.command("ping")
    return _db


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB is not initialized. Call init_mongo() first.")
    return _db


async def close_mongo() -> None:
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None
