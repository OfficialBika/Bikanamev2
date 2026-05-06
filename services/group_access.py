from __future__ import annotations

import time
from aiogram.types import Message
from config import settings
from database.mongo import get_db
from utils.ttl_cache import TTLCache

_group_cache: TTLCache[int, bool] = TTLCache(10000, settings.gapprove_cache_seconds)


def is_owner_or_sudo(user_id: int | None) -> bool:
    return bool(user_id and (user_id in settings.owner_ids or user_id in settings.sudo_ids))


async def remember_user(user_id: int | None, username: str | None = None) -> None:
    if not user_id:
        return
    db = get_db()
    await db["known_users"].update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "username": username, "updated_at": time.time()}, "$setOnInsert": {"created_at": time.time()}},
        upsert=True,
    )


async def is_approved_group(chat_id: int) -> bool:
    if not settings.enable_gapprove:
        return True
    if settings.support_group_id and chat_id == settings.support_group_id:
        return True
    cached = _group_cache.get(chat_id)
    if cached is not None:
        return cached
    db = get_db()
    doc = await db["settings"].find_one({"key": f"gapprove:{chat_id}"})
    ok = bool(doc and doc.get("enabled", True))
    _group_cache.set(chat_id, ok)
    return ok


async def set_group_approved(chat_id: int, enabled: bool = True) -> None:
    db = get_db()
    await db["settings"].update_one(
        {"key": f"gapprove:{chat_id}"},
        {"$set": {"enabled": enabled, "updated_at": time.time()}},
        upsert=True,
    )
    _group_cache.set(chat_id, enabled)


async def can_auto_lookup(message: Message) -> bool:
    if not settings.auto_lookup_enabled:
        return False
    if message.chat.type == "private":
        return settings.auto_lookup_in_dm
    if settings.support_group_id and message.chat.id == settings.support_group_id and settings.auto_lookup_in_support_group:
        return True
    if settings.auto_lookup_only_approved_groups:
        return await is_approved_group(message.chat.id)
    return True
