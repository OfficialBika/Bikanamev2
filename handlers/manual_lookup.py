from __future__ import annotations

import re
import time

from aiogram import F, Router
from aiogram.types import Message
from config import settings
from locales import en, my
from services.force_join import require_join
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from services.source_blocker import blocked_source_text, is_blocked_source
from utils.telegram_safe import safe_reply

router = Router(name="manual_lookup")

# Keep /name commands, plus unique source commands that are safe for scoped manual lookup.
MANUAL_RE = re.compile(
    r"^(?P<cmd>/waifu|/w|\.wa|\.w|/name|\.name|/loot|/bika|/pick|/ziceko|/orin|/dao)"
    r"(?:@(?P<bot>[A-Za-z0-9_]+))?"
    r"(?:\s|$)",
    re.I,
)

_DEDUPE_TTL_SECONDS = 20
_seen_manual_lookup: dict[str, float] = {}


def _cleanup_seen(now: float) -> None:
    for key, ts in list(_seen_manual_lookup.items()):
        if now - ts > _DEDUPE_TTL_SECONDS:
            _seen_manual_lookup.pop(key, None)


def _chat_id(message: Message) -> int:
    return int(getattr(message.chat, "id", 0) or 0)


def _sender_id(message: Message) -> int:
    if message.from_user:
        return int(message.from_user.id)
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat and getattr(sender_chat, "id", None):
        return int(sender_chat.id)
    return 0


def _manual_unique_key(message: Message) -> str:
    return f"chat:{_chat_id(message)}:sender:{_sender_id(message)}:msg:{message.message_id}"


def _already_processed(message: Message) -> bool:
    now = time.monotonic()
    _cleanup_seen(now)
    key = _manual_unique_key(message)
    if key in _seen_manual_lookup:
        return True
    _seen_manual_lookup[key] = now
    return False


def _is_private_chat(message: Message) -> bool:
    chat_type = getattr(message.chat, "type", "") if message.chat else ""
    value = getattr(chat_type, "value", chat_type)
    return str(value).lower() == "private"


def _command_match(message: Message):
    return MANUAL_RE.match(message.text or "")


async def _targets_this_bot(message: Message) -> bool:
    match = _command_match(message)
    if not match:
        return False
    mention = match.group("bot")
    if not mention:
        return True
    mention = mention.lower().lstrip("@")
    configured = (settings.bot_username or "").lower().lstrip("@")
    if configured:
        return mention == configured
    try:
        me = await message.bot.get_me()
        return mention == ((me.username or "").lower().lstrip("@"))
    except Exception:
        return False


@router.message(F.text.regexp(MANUAL_RE))
async def manual_lookup(message: Message) -> None:
    if not await _targets_this_bot(message):
        return
    if _already_processed(message):
        return

    target = message.reply_to_message or message
    if is_blocked_source(target):
        await safe_reply(message, blocked_source_text())
        return

    if not await require_join(message):
        return

    result = await lookup_service.lookup_message(message.bot, message, manual=True)

    if result.reason == "blocked_source":
        await safe_reply(message, blocked_source_text())
        return
    if result.reason == "no_media":
        if _is_private_chat(message):
            await safe_reply(message, f"{my.NO_MEDIA}\n{en.NO_MEDIA}")
        return
    if not result.item:
        await safe_reply(message, f"{my.NOT_FOUND}\n{en.NOT_FOUND}")
        return

    await safe_reply(message, format_result(result.item), reply_markup=result_buttons(result.item), disable_web_page_preview=True)
