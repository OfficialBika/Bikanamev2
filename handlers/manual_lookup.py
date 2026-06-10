from __future__ import annotations

import re
import time
from aiogram import F, Router
from aiogram.types import Message
from locales import en, my
from services.force_join import require_join
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from utils.telegram_safe import safe_reply

router = Router(name="manual_lookup")

# Manual lookup commands.
# /bika and /pick are included so source-command lookup can stay scoped and fast.
MANUAL_RE = re.compile(r"^(?:/waifu|/w|\.wa|\.w|/name|\.name|/loot|/bika|/pick)(?:\s|$)", re.I)

# Same manual command update ကို short time အတွင်း duplicate reply မထွက်အောင် cache.
_DEDUPE_TTL_SECONDS = 20
_seen_manual_lookup: dict[str, float] = {}


def _cleanup_seen(now: float) -> None:
    expired = [key for key, ts in _seen_manual_lookup.items() if now - ts > _DEDUPE_TTL_SECONDS]
    for key in expired:
        _seen_manual_lookup.pop(key, None)


def _manual_unique_key(message: Message) -> str:
    # Same message update duplicated / router included twice ဖြစ်ရင် message_id တူနေမယ်။
    # Reply target info ကိုလည်းထည့်ထားလို့ album/reply cases မှာ key ပိုတိကျမယ်။
    reply = message.reply_to_message
    reply_id = getattr(reply, "message_id", 0) or 0

    if reply:
        if reply.photo:
            return f"{message.chat.id}:manual:{message.message_id}:reply_photo:{reply.photo[-1].file_unique_id}"
        if reply.video:
            return f"{message.chat.id}:manual:{message.message_id}:reply_video:{reply.video.file_unique_id}"
        if reply.animation:
            return f"{message.chat.id}:manual:{message.message_id}:reply_animation:{reply.animation.file_unique_id}"
        if reply.document:
            return f"{message.chat.id}:manual:{message.message_id}:reply_document:{reply.document.file_unique_id}"

    return f"{message.chat.id}:manual:{message.message_id}:reply:{reply_id}"


def _already_processed(message: Message) -> bool:
    now = time.monotonic()
    _cleanup_seen(now)

    key = _manual_unique_key(message)
    if key in _seen_manual_lookup:
        return True

    _seen_manual_lookup[key] = now
    return False


@router.message(F.text.regexp(MANUAL_RE))
async def manual_lookup(message: Message) -> None:
    # Router duplicate include / same update duplicate delivery ဖြစ်ရင် reply နှစ်ခါမထွက်အောင် ကာမယ်။
    if _already_processed(message):
        return

    if not await require_join(message):
        return

    result = await lookup_service.lookup_message(message.bot, message, manual=True)

    if result.reason == "no_media":
        await safe_reply(message, f"{my.NO_MEDIA}\n{en.NO_MEDIA}")
        return

    if not result.item:
        await safe_reply(message, f"{my.NOT_FOUND}\n{en.NOT_FOUND}")
        return

    await safe_reply(
        message,
        format_result(result.item),
        reply_markup=result_buttons(result.item),
        disable_web_page_preview=True,
    )
