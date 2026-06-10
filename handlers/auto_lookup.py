from __future__ import annotations

import time

from aiogram import F, Router
from aiogram.types import Message
from locales import en, my
from services.force_join import require_join
from services.group_access import can_auto_lookup, remember_user
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from utils.telegram_safe import safe_reply

router = Router(name="auto_lookup")

# Prevent duplicate auto-lookup replies for the same Telegram update/message.
#
# Important:
# - We do NOT dedupe by file_unique_id, because two different users may send the
#   same media and both users should get one reply each.
# - Normal media uses chat_id + sender_id + message_id, so only the same duplicated
#   update/message is skipped.
# - Albums use chat_id + sender_id + media_group_id, so a single album send produces
#   one auto-lookup reply, while another user sending the same media still gets a reply.
_DEDUPE_TTL_SECONDS = 20
_seen_auto_lookup: dict[str, float] = {}


def _cleanup_seen(now: float) -> None:
    expired = [key for key, ts in _seen_auto_lookup.items() if now - ts > _DEDUPE_TTL_SECONDS]
    for key in expired:
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
    if media_group_id:
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
        return

    # Auto lookup မှာ DB ထဲ မတွေ့တဲ့ media တွေကို Not Found ပြန်ပို့မယ်။
    # Duplicate dedupe / force-join / group access logic တွေကို မထိခိုက်အောင်
    # lookup ပြီး result မရှိတဲ့ case မှာပဲ reply ပြန်ထားပါတယ်။
    await safe_reply(message, f"{my.NOT_FOUND}\n{en.NOT_FOUND}")
