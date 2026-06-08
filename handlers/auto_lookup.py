from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.types import Message
from services.force_join import require_join
from services.group_access import can_auto_lookup, remember_user
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from utils.telegram_safe import safe_reply

router = Router(name="auto_lookup")

# Prevent duplicate auto-lookup replies for the same media/update in a short window.
# This helps when Telegram sends duplicate updates, media albums are processed item-by-item,
# or the same forwarded media is received twice very quickly.
_DEDUPE_TTL_SECONDS = 20
_seen_auto_lookup: dict[str, float] = {}


def _cleanup_seen(now: float) -> None:
    expired = [key for key, ts in _seen_auto_lookup.items() if now - ts > _DEDUPE_TTL_SECONDS]
    for key in expired:
        _seen_auto_lookup.pop(key, None)


def _file_unique_id_from_message(message: Message) -> str:
    if message.photo:
        return getattr(message.photo[-1], "file_unique_id", "") or getattr(message.photo[-1], "file_id", "") or ""
    if message.video:
        return getattr(message.video, "file_unique_id", "") or getattr(message.video, "file_id", "") or ""
    if message.animation:
        return getattr(message.animation, "file_unique_id", "") or getattr(message.animation, "file_id", "") or ""
    if message.document:
        return getattr(message.document, "file_unique_id", "") or getattr(message.document, "file_id", "") or ""
    return ""


def _media_unique_key(message: Message) -> str:
    chat_id = getattr(message.chat, "id", 0) if message.chat else 0

    # For Telegram albums, only auto-lookup the first item we receive from the same media_group_id.
    media_group_id = getattr(message, "media_group_id", None)
    if media_group_id:
        return f"chat:{chat_id}:album:{media_group_id}"

    file_uid = _file_unique_id_from_message(message)
    if file_uid:
        return f"chat:{chat_id}:file:{file_uid}"

    return f"chat:{chat_id}:msg:{message.message_id}"


def _already_processed(message: Message) -> bool:
    now = time.monotonic()
    _cleanup_seen(now)

    key = _media_unique_key(message)
    if key in _seen_auto_lookup:
        return True

    _seen_auto_lookup[key] = now
    return False


def _media_filter(message: Message) -> bool:
    if message.text:
        return False
    return bool(message.photo or message.video or message.animation or message.document)


@router.message(F.func(_media_filter))
async def auto_lookup(message: Message) -> None:
    if _already_processed(message):
        return

    if message.from_user:
        await remember_user(message.from_user.id, message.from_user.username)

    if not await can_auto_lookup(message):
        return

    if not await require_join(message):
        return

    result = await lookup_service.lookup_message(message.bot, message, manual=False)
    if result.item:
        await safe_reply(
            message,
            format_result(result.item),
            reply_markup=result_buttons(result.item),
            disable_web_page_preview=True,
        )
