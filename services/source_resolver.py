from __future__ import annotations

import re
from aiogram.types import Message
from config import BOT_SOURCE_COLLECTION, BOT_SOURCE_OUTPUT_COMMAND, COLLECTION_TO_OUTPUT_COMMAND, COMMAND_TO_COLLECTION, settings

MANUAL_COMMANDS = {"/waifu", "/w", ".wa", ".w", "/name", ".name"}
USING_RE = re.compile(r"(?:using|use|hint|full)\s*[:：]?\s*(/[a-zA-Z_]+)", re.I)
CMD_RE = re.compile(r"(^|\s)(/[a-zA-Z_]+)(?=\s|$)")


def command_from_text(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip()
    first = t.split(maxsplit=1)[0].lower() if t else ""
    if first in COMMAND_TO_COLLECTION:
        return first
    m = USING_RE.search(t) or CMD_RE.search(t)
    if m:
        cmd = m.group(m.lastindex or 1).lower()
        if cmd in COMMAND_TO_COLLECTION or cmd in {"/grab", "/guess", "/loot"}:
            return cmd
    return None


def collection_from_command(cmd: str | None) -> str | None:
    if not cmd:
        return None
    return COMMAND_TO_COLLECTION.get(cmd.lower())


def _normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return "@" + username.lower().lstrip("@")


def source_username(message: Message) -> str | None:
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin else None
    username = getattr(chat, "username", None) if chat else None
    if username:
        return _normalize_username(username)
    if message.via_bot and message.via_bot.username:
        return _normalize_username(message.via_bot.username)
    return None


def source_title(message: Message) -> str | None:
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin else None
    title = getattr(chat, "title", None) if chat else None
    return title or None


def _custom_source_command(message: Message) -> str | None:
    uname = source_username(message)
    title = source_title(message) or ""
    text = f"{title}\n{message.caption or message.text or ''}".lower()
    if uname and uname in settings.forward_source_commands:
        return settings.forward_source_commands[uname]
    for key, cmd in settings.forward_source_commands.items():
        if key.startswith("@"):
            continue
        if "|" in key:
            parts = [p.strip().lower() for p in key.split("|") if p.strip()]
            if all(p in text for p in parts):
                return cmd
        elif key.lower() in text:
            return cmd
    return None


def resolve_collection(message: Message) -> str | None:
    username = source_username(message)
    if username and username in BOT_SOURCE_COLLECTION:
        return BOT_SOURCE_COLLECTION[username]
    custom_cmd = _custom_source_command(message)
    if custom_cmd:
        col = collection_from_command(custom_cmd)
        if col:
            return col
    text = message.caption or message.text or ""
    cmd = command_from_text(text)
    return collection_from_command(cmd)


def output_command_from_message(message: Message, collection: str | None = None) -> str | None:
    """Return a command override for the final result text.

    Example: @CharacterLootBot stores/looks up from items_character_seizer,
    but the user-facing command must be /loot instead of /seize.
    """
    username = source_username(message)
    if username and username in BOT_SOURCE_OUTPUT_COMMAND:
        return BOT_SOURCE_OUTPUT_COMMAND[username]

    custom_cmd = _custom_source_command(message)
    if custom_cmd and collection_from_command(custom_cmd) == collection:
        return custom_cmd

    text = message.caption or message.text or ""
    cmd = command_from_text(text)
    if cmd and collection_from_command(cmd) == collection:
        return cmd
    return None


def default_collection() -> str:
    return collection_from_command(settings.default_command) or "items_characters_hallow"


def all_lookup_collections() -> list[str]:
    return list(COLLECTION_TO_OUTPUT_COMMAND.keys())
