from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
try:
    from aiogram.types import CopyTextButton
except Exception:
    CopyTextButton = None  # type: ignore

from config import settings
from services.snapshot_cache import ItemSnapshot
from utils.text import first_token, h


def _copy_button(text: str, value: str) -> InlineKeyboardButton:
    if CopyTextButton is not None:
        return InlineKeyboardButton(text=text, copy_text=CopyTextButton(text=value))
    return InlineKeyboardButton(text=text, callback_data="noop")


def format_result(item: ItemSnapshot) -> str:
    command = item.command or "/name"
    lines = [
        f"<b>NAME :</b> <code>{h(item.name)}</code>",
        "────────────────",
        f"🔹 <b>Hint :</b> <code>{h(command + ' ' + first_token(item.name))}</code>",
        f"🔸 <b>Full :</b> <code>{h(command + ' ' + item.name)}</code>",
    ]
    if settings.show_source_in_result:
        lines.insert(1, f"<b>SOURCE :</b> <code>{h(command)}</code>")
    if settings.owner_username:
        owner = settings.owner_username if settings.owner_username.startswith("@") else "@" + settings.owner_username
        username = owner.lstrip("@")
        lines.append(f"\nPowered by <a href=\"https://t.me/{h(username)}\">{h(owner)}</a>")
    return "\n".join(lines)


def result_buttons(item: ItemSnapshot) -> InlineKeyboardMarkup | None:
    if settings.fast_reply_mode or not settings.enable_copy_buttons:
        return None
    command = item.command or "/name"
    hint = f"{command} {first_token(item.name)}"
    full = f"{command} {item.name}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        _copy_button("📋 Copy Hint", hint),
        _copy_button("📋 Copy Full", full),
    ]])
