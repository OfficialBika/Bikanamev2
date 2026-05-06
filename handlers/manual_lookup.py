from __future__ import annotations

import re
from aiogram import F, Router
from aiogram.types import Message
from locales import en, my
from services.force_join import require_join
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from utils.telegram_safe import safe_reply

router = Router(name="manual_lookup")
MANUAL_RE = re.compile(r"^(?:/waifu|/w|\.wa|\.w|/name|\.name|/loot)(?:\s|$)", re.I)


@router.message(F.text.regexp(MANUAL_RE))
async def manual_lookup(message: Message) -> None:
    if not await require_join(message):
        return
    result = await lookup_service.lookup_message(message.bot, message, manual=True)
    if result.reason == "no_media":
        await safe_reply(message, f"{my.NO_MEDIA}\n{en.NO_MEDIA}")
        return
    if not result.item:
        await safe_reply(message, f"{my.NOT_FOUND}\n{en.NOT_FOUND}")
        return
    await safe_reply(message, format_result(result.item), reply_markup=result_buttons(result.item), disable_web_page_preview=True)
