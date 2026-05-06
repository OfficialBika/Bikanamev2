from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from services.group_access import is_owner_or_sudo, set_group_approved
from services.snapshot_cache import snapshot
from utils.telegram_safe import safe_reply

router = Router(name="admin")


@router.message(Command("gapprove"))
async def gapprove(message: Message) -> None:
    if not is_owner_or_sudo(message.from_user.id if message.from_user else None):
        return
    if message.chat.type == "private":
        await safe_reply(message, "Use /gapprove inside the target group.")
        return
    await set_group_approved(message.chat.id, True)
    await safe_reply(message, "✅ This group is approved for auto lookup.")


@router.message(Command("gunapprove"))
async def gunapprove(message: Message) -> None:
    if not is_owner_or_sudo(message.from_user.id if message.from_user else None):
        return
    if message.chat.type == "private":
        await safe_reply(message, "Use /gunapprove inside the target group.")
        return
    await set_group_approved(message.chat.id, False)
    await safe_reply(message, "✅ This group is removed from auto lookup.")


@router.message(Command("refresh"))
async def refresh_snapshot(message: Message) -> None:
    if not is_owner_or_sudo(message.from_user.id if message.from_user else None):
        return
    await safe_reply(message, "Refreshing snapshot...")
    await snapshot.refresh()
    await safe_reply(message, f"✅ Snapshot refreshed. Items: {snapshot.count}")
