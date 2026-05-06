from __future__ import annotations

import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from config import settings
from locales import en, my
from utils.ttl_cache import TTLCache

log = logging.getLogger(__name__)
_join_cache: TTLCache[str, bool] = TTLCache(50000, settings.force_join_cache_seconds)


def _channel_button(channel: str) -> InlineKeyboardButton:
    if channel.startswith("@"):
        return InlineKeyboardButton(text=f"📢 {channel}", url=f"https://t.me/{channel.lstrip('@')}")
    return InlineKeyboardButton(text="📢 Join Channel", url=str(channel))


async def bot_username(bot: Bot) -> str:
    if settings.bot_username:
        return settings.bot_username
    me = await bot.get_me()
    return me.username or ""


async def has_joined(bot: Bot, user_id: int) -> bool:
    if not settings.enable_force_join or not settings.force_join_channels:
        return True
    key = f"{user_id}:{'|'.join(settings.force_join_channels)}"
    cached = _join_cache.get(key)
    if cached is not None:
        return cached
    for channel in settings.force_join_channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
                _join_cache.set(key, False)
                return False
        except Exception:
            log.warning("force join check failed for %s", channel, exc_info=True)
            _join_cache.set(key, False)
            return False
    _join_cache.set(key, True)
    return True


def dm_force_join_keyboard() -> InlineKeyboardMarkup:
    rows = [[_channel_button(ch)] for ch in settings.force_join_channels]
    if settings.support_group_username:
        rows.append([InlineKeyboardButton(text="👥 Support Group", url=f"https://t.me/{settings.support_group_username.lstrip('@')}")])
    rows.append([InlineKeyboardButton(text="✅ Joined / Check Again", callback_data="force_join_check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def group_dm_keyboard(bot: Bot) -> InlineKeyboardMarkup:
    username = await bot_username(bot)
    link = f"https://t.me/{username}?start={settings.force_join_dm_start_param}" if username else "https://t.me/"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🤖 Open Bot DM", url=link)]])


def dm_force_join_text() -> str:
    return f"{my.FORCE_JOIN_TEXT}\n\n{en.FORCE_JOIN_TEXT}"


def group_force_join_text() -> str:
    return f"{my.GROUP_FORCE_JOIN_TEXT}\n{en.GROUP_FORCE_JOIN_TEXT}"


async def require_join(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else 0
    if await has_joined(message.bot, user_id):
        return True
    if message.chat.type == "private":
        await message.answer(dm_force_join_text(), reply_markup=dm_force_join_keyboard())
    else:
        await message.reply(group_force_join_text(), reply_markup=await group_dm_keyboard(message.bot))
    return False
