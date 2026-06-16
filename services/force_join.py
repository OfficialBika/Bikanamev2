from __future__ import annotations

import logging
import os
from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import settings
from locales import en, my
from utils.ttl_cache import TTLCache
from services.free_users import is_free_user

log = logging.getLogger(__name__)
router = Router(name="force_join")

# Positive join verification cache only.
# User requested: once verified joined, do not check again for 1 day.
# Important: negative/not-joined results are NOT cached, so pressing
# "Joined / Check Again" always re-checks Telegram immediately.
POSITIVE_JOIN_CACHE_SECONDS = int(os.getenv("FORCE_JOIN_POSITIVE_CACHE_SECONDS", "86400"))
_join_cache: TTLCache[str, bool] = TTLCache(50000, POSITIVE_JOIN_CACHE_SECONDS)


def _force_join_cache_key(user_id: int) -> str:
    return f"forcejoin:{user_id}:{'|'.join(settings.force_join_channels)}"


def _channel_button(channel: str) -> InlineKeyboardButton:
    if channel.startswith("@"):
        return InlineKeyboardButton(text=f"📢 {channel}", url=f"https://t.me/{channel.lstrip('@')}")
    return InlineKeyboardButton(text="📢 Join Channel", url=str(channel))


async def bot_username(bot: Bot) -> str:
    if settings.bot_username:
        return settings.bot_username
    me = await bot.get_me()
    return me.username or ""


async def _check_all_channels(bot: Bot, user_id: int) -> bool:
    """Live Telegram membership check. No cache is read/written here."""
    for channel in settings.force_join_channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
                return False
        except Exception:
            # Do not cache failures as False. Network/admin/channel errors should not
            # lock a user out for 1 day. Log once and ask user to retry.
            log.warning("force join live check failed for %s", channel, exc_info=True)
            return False
    return True


async def has_joined(bot: Bot, user_id: int, *, force_refresh: bool = False) -> bool:
    """Return True only when user has joined all required channels.

    Behavior:
    - Force join disabled / no channels => True
    - Free users bypass force join
    - Positive joined result is cached for 1 day
    - Not-joined result is never cached
    - force_refresh=True always checks Telegram again, used by the button
    """
    if not settings.enable_force_join or not settings.force_join_channels:
        return True

    # Free users bypass force-join check.
    if await is_free_user(user_id):
        return True

    key = _force_join_cache_key(user_id)
    if not force_refresh:
        cached = _join_cache.get(key)
        if cached is True:
            return True

    joined = await _check_all_channels(bot, user_id)
    if joined:
        _join_cache.set(key, True)
    return joined


def dm_force_join_keyboard() -> InlineKeyboardMarkup:
    rows = [[_channel_button(ch)] for ch in settings.force_join_channels]
    if settings.support_group_username:
        rows.append([
            InlineKeyboardButton(
                text="👥 Support Group",
                url=f"https://t.me/{settings.support_group_username.lstrip('@')}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="✅ Joined / Check Again",
            callback_data="force_join_check",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def group_dm_keyboard(bot: Bot) -> InlineKeyboardMarkup:
    username = await bot_username(bot)
    link = f"https://t.me/{username}?start={settings.force_join_dm_start_param}" if username else "https://t.me/"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🤖 Open Bot DM", url=link)]]
    )


def dm_force_join_text() -> str:
    return f"{my.FORCE_JOIN_TEXT}\n\n{en.FORCE_JOIN_TEXT}"


def group_force_join_text() -> str:
    return f"{my.GROUP_FORCE_JOIN_TEXT}\n{en.GROUP_FORCE_JOIN_TEXT}"


def verified_text() -> str:
    return "✅ Join verified.\n\nအခု Bot ကို ဆက်သုံးလို့ရပါပြီ။"


async def require_join(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else 0
    if await has_joined(message.bot, user_id):
        return True

    if message.chat.type == "private":
        await message.answer(dm_force_join_text(), reply_markup=dm_force_join_keyboard())
    else:
        await message.reply(group_force_join_text(), reply_markup=await group_dm_keyboard(message.bot))
    return False


@router.callback_query(F.data == "force_join_check")
async def force_join_check_callback(callback: CallbackQuery) -> None:
    """Re-check button for force join.

    Pressing the button always re-checks Telegram live. If joined, cache True for
    1 day. If not joined, do not cache False and show join buttons again.
    """
    user_id = callback.from_user.id if callback.from_user else 0
    if not user_id:
        await callback.answer("User not found", show_alert=True)
        return

    joined = await has_joined(callback.bot, user_id, force_refresh=True)
    if joined:
        await callback.answer("✅ Verified", show_alert=False)
        if callback.message:
            try:
                await callback.message.edit_text(verified_text())
            except Exception:
                try:
                    await callback.message.answer(verified_text())
                except Exception:
                    pass
        return

    await callback.answer("မ join ရသေးပါ။ Channel ကို join ပြီးမှ ပြန်နှိပ်ပါ။", show_alert=True)
    if callback.message:
        try:
            await callback.message.edit_text(dm_force_join_text(), reply_markup=dm_force_join_keyboard())
        except Exception:
            try:
                await callback.message.answer(dm_force_join_text(), reply_markup=dm_force_join_keyboard())
            except Exception:
                pass
