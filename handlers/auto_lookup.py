from __future__ import annotations

import logging
import os
import time

from aiogram import F, Router
from aiogram.types import Message

from locales import en, my
from services.force_join import require_join
from services.group_access import can_auto_lookup, remember_user
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from services.source_blocker import blocked_source_text, is_blocked_source
from utils.telegram_safe import safe_reply

router = Router(name="auto_lookup")
log = logging.getLogger(__name__)

_DEDUPE_TTL_SECONDS = int(os.getenv("AUTO_LOOKUP_DEDUPE_TTL_SECONDS", "20") or 20)
_DEDUPE_ALBUM = os.getenv("AUTO_LOOKUP_DEDUPE_ALBUM", "false").strip().lower() in {"1", "true", "yes", "y", "on"}
_REPLY_NOT_FOUND = os.getenv("AUTO_LOOKUP_REPLY_NOT_FOUND", "true").strip().lower() in {"1", "true", "yes", "y", "on"}
_seen_auto_lookup: dict[str, float] = {}


def _cleanup_seen(now: float) -> None:
    for key, ts in list(_seen_auto_lookup.items()):
        if now - ts > _DEDUPE_TTL_SECONDS:
            _seen_auto_lookup.pop(key, None)


def _chat_id(message: Message) -> int:
    return int(getattr(message.chat, "id", 0) or 0)


def _sender_id(message: Message) -> int:
    if message.from_user:
        return int(message.from_user.id)
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat and getattr(sender_chat, "id", None):
        return int(sender_chat.id)
    return 0


def _media_unique_key(message: Message) -> str:
    chat_id = _chat_id(message)
    sender_id = _sender_id(message)
    media_group_id = getattr(message, "media_group_id", None)
    if _DEDUPE_ALBUM and media_group_id:
        return f"chat:{chat_id}:sender:{sender_id}:album:{media_group_id}"
    return f"chat:{chat_id}:sender:{sender_id}:msg:{message.message_id}"


def _already_processed(message: Message) -> bool:
    now = time.monotonic()
    _cleanup_seen(now)
    key = _media_unique_key(message)
    if key in _seen_auto_lookup:
        return True
    _seen_auto_lookup[key] = now
    return False


def _is_supported_document(message: Message) -> bool:
    document = getattr(message, "document", None)
    if not document:
        return False
    mime_type = str(getattr(document, "mime_type", "") or "").lower()
    if mime_type.startswith("image/") or mime_type.startswith("video/"):
        return True
    file_name = str(getattr(document, "file_name", "") or "").lower()
    return file_name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mkv", ".mov", ".webm"))


def _media_filter(message: Message) -> bool:
    return bool(
        getattr(message, "photo", None)
        or getattr(message, "video", None)
        or getattr(message, "animation", None)
        or _is_supported_document(message)
    )


async def _reply_result(message: Message, result) -> None:
    if result.item:
        await safe_reply(message, format_result(result.item), reply_markup=result_buttons(result.item), disable_web_page_preview=True)
        return
    if result.reason == "blocked_source":
        await safe_reply(message, blocked_source_text())
        return
    if _REPLY_NOT_FOUND and result.reason != "no_media":
        await safe_reply(message, f"{my.NOT_FOUND}\n{en.NOT_FOUND}")


@router.message(F.func(_media_filter))
async def auto_lookup(message: Message) -> None:
    started = time.perf_counter()

    if message.from_user:
        await remember_user(message.from_user.id, message.from_user.username)

    if not await can_auto_lookup(message):
        log.debug("auto lookup skipped: access denied | chat=%s msg=%s", _chat_id(message), getattr(message, "message_id", None))
        return

    if is_blocked_source(message):
        if not _already_processed(message):
            await safe_reply(message, blocked_source_text())
        return

    if not await require_join(message):
        log.debug("auto lookup skipped: force join required | chat=%s msg=%s", _chat_id(message), getattr(message, "message_id", None))
        return

    if _already_processed(message):
        log.debug("auto lookup skipped: duplicate | chat=%s msg=%s", _chat_id(message), getattr(message, "message_id", None))
        return

    try:
        result = await lookup_service.lookup_message(message.bot, message, manual=False)
    except Exception:
        log.exception("auto lookup failed | chat=%s msg=%s", _chat_id(message), getattr(message, "message_id", None))
        if _REPLY_NOT_FOUND:
            await safe_reply(message, f"{my.NOT_FOUND}\n{en.NOT_FOUND}")
        return

    await _reply_result(message, result)
    elapsed_ms = (time.perf_counter() - started) * 1000
    log.debug("auto lookup finished | chat=%s msg=%s reason=%s hit=%s elapsed=%.1fms", _chat_id(message), getattr(message, "message_id", None), getattr(result, "reason", "-"), bool(getattr(result, "item", None)), elapsed_ms)
