from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import settings
from services.free_users import add_free_user, remove_free_user, is_free_user
from utils.telegram_safe import safe_reply


router = Router(name="free")


def _target_from_reply(message: Message) -> tuple[int | None, str]:
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        name = user.full_name or user.username or str(user.id)
        return user.id, name
    return None, ""


def _target_from_args(args: str | None) -> int | None:
    raw = (args or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _is_owner(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else 0
    return user_id in settings.owner_ids


@router.message(Command("free"))
async def free_cmd(message: Message, command: CommandObject) -> None:
    if not _is_owner(message):
        return

    target_id, target_name = _target_from_reply(message)

    if not target_id:
        target_id = _target_from_args(command.args)
        target_name = str(target_id or "")

    if not target_id:
        await safe_reply(
            message,
            "Usage:\nReply user + /free\nor\n/free 123456789"
        )
        return

    await add_free_user(
        user_id=target_id,
        added_by=message.from_user.id,
        reason="force_join_bypass",
    )

    await safe_reply(
        message,
        f"✅ Force-join free added\nUser: {target_name or target_id}\nID: <code>{target_id}</code>",
        parse_mode="HTML",
    )


@router.message(Command("unfree"))
async def unfree_cmd(message: Message, command: CommandObject) -> None:
    if not _is_owner(message):
        return

    target_id, target_name = _target_from_reply(message)

    if not target_id:
        target_id = _target_from_args(command.args)
        target_name = str(target_id or "")

    if not target_id:
        await safe_reply(
            message,
            "Usage:\nReply user + /unfree\nor\n/unfree 123456789"
        )
        return

    removed = await remove_free_user(target_id)

    await safe_reply(
        message,
        (
            f"✅ Force-join free removed\nUser: {target_name or target_id}\nID: <code>{target_id}</code>"
            if removed
            else f"⚠️ This user was not in free list\nID: <code>{target_id}</code>"
        ),
        parse_mode="HTML",
    )


@router.message(Command("freecheck"))
async def freecheck_cmd(message: Message, command: CommandObject) -> None:
    if not _is_owner(message):
        return

    target_id, target_name = _target_from_reply(message)

    if not target_id:
        target_id = _target_from_args(command.args)
        target_name = str(target_id or "")

    if not target_id:
        await safe_reply(
            message,
            "Usage:\nReply user + /freecheck\nor\n/freecheck 123456789"
        )
        return

    ok = await is_free_user(target_id)

    await safe_reply(
        message,
        f"User: {target_name or target_id}\nID: <code>{target_id}</code>\nFree: <b>{'YES' if ok else 'NO'}</b>",
        parse_mode="HTML",
    )
