from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from services.force_join import require_join
from services.group_access import can_auto_lookup, remember_user
from services.lookup_service import lookup_service
from services.result_formatter import format_result, result_buttons
from utils.telegram_safe import safe_reply

router = Router(name="auto_lookup")


def _media_filter(message: Message) -> bool:
    if message.text:
        return False
    return bool(message.photo or message.video or message.animation or message.document)


@router.message(F.func(_media_filter))
async def auto_lookup(message: Message) -> None:
    if message.from_user:
        await remember_user(message.from_user.id, message.from_user.username)
    if not await can_auto_lookup(message):
        return
    if not await require_join(message):
        return
    result = await lookup_service.lookup_message(message.bot, message, manual=False)
    if result.item:
        await safe_reply(message, format_result(result.item), reply_markup=result_buttons(result.item), disable_web_page_preview=True)
