from __future__ import annotations

import re
from aiogram.types import Message
from config import (
    BOT_SOURCE_COLLECTION,
    BOT_SOURCE_OUTPUT_COMMAND,
    COLLECTION_TO_OUTPUT_COMMAND,
    COMMAND_TO_COLLECTION,
    settings,
)

# Manual lookup commands. /loop is intentionally NOT included.
MANUAL_COMMANDS = {"/waifu", "/w", ".wa", ".w", "/name", ".name", "/bika", "/loot"}

USING_RE = re.compile(r"(?:using|use|hint|full)\s*[:：]?\s*(/[a-zA-Z_]+)", re.I)
CMD_RE = re.compile(r"(^|\s)(/[a-zA-Z_]+)(?=\s|$)")


# Telegram forward display title/name based mapping.
# This fixes forwards where Telegram shows only "Forwarded from <Display Name>"
# and does not expose username.
TITLE_SOURCE_COLLECTION = {
    # 1
    "character catcher": "items_character_catcher",
    "character catcher bot": "items_character_catcher",
    "characters catcher": "items_character_catcher",
    "characters catcher bot": "items_character_catcher",

    # 2
    "character hallow": "items_characters_hallow",
    "character hallow bot": "items_characters_hallow",
    "characters hallow": "items_characters_hallow",
    "characters hallow bot": "items_characters_hallow",
    "hallow upload": "items_characters_hallow",
    "hallow uploads": "items_characters_hallow",

    # 3
    "character capture": "items_capture_character",
    "character capture bot": "items_capture_character",
    "capture character": "items_capture_character",
    "capture character bot": "items_capture_character",
    "capture database": "items_capture_character",

    # 4 / 14 share seizer collection
    "character seize": "items_character_seizer",
    "character seize bot": "items_character_seizer",
    "character seizer": "items_character_seizer",
    "character seizer bot": "items_character_seizer",
    "seizer database": "items_character_seizer",
    "character loot": "items_character_seizer",
    "character loot bot": "items_character_seizer",
    "character looter": "items_character_seizer",
    "character looter bot": "items_character_seizer",

    # 5: normal + fancy Telegram title variants
    "husbando grabber": "items_husbando_grabber",
    "husbando grabber bot": "items_husbando_grabber",
    "ʜᴜsʙᴀɴᴅᴏ ɢʀᴀʙʙᴇʀ": "items_husbando_grabber",
    "ʜᴜsʙᴀɴᴅᴏ ɢʀᴀʙʙᴇʀ ʙᴏᴛ": "items_husbando_grabber",

    # 6-7
    "grab your waifu": "items_grab_your_waifu",
    "grab your waifu bot": "items_grab_your_waifu",
    "grab your husbando": "items_grab_your_husbando",
    "grab your husbando bot": "items_grab_your_husbando",

    # 8-13
    "takers bot": "items_takers_character",
    "takers character": "items_takers_character",
    "takers character bot": "items_takers_character",
    "catch your husbando": "items_catch_your_husbando",
    "catch your husbando bot": "items_catch_your_husbando",
    "smash your character": "items_smash_character",
    "smash your character bot": "items_smash_character",
    "smash character": "items_smash_character",
    "smash character bot": "items_smash_character",
    "grab garden": "items_waifux_grab",
    "waifux grab": "items_waifux_grab",
    "waifuxgrab": "items_waifux_grab",
    "waifux grab bot": "items_waifux_grab",
    "catch your waifu": "items_catch_your_waifu",
    "catch your waifu bot": "items_catch_your_waifu",
    "waifu grabber": "items_waifu_grabber",
    "waifu grabber bot": "items_waifu_grabber",
    "ᴡᴀɪғᴜ ɢʀᴀʙʙᴇʀ": "items_waifu_grabber",
    "ᴡᴀɪғᴜ ɢʀᴀʙʙᴇʀ ʙᴏᴛ": "items_waifu_grabber",
}

TITLE_OUTPUT_COMMAND = {
    "character loot": "/loot",
    "character loot bot": "/loot",
    "character looter": "/loot",
    "character looter bot": "/loot",
}


def _clean_title(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).lower().strip()
    s = s.replace("_", " ")
    # Remove decorative brackets/quotes but keep unicode small-caps text.
    s = re.sub(r"[『』「」'\"`´|•·。、,;:!¡?¿()\[\]{}<>]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _title_to_collection(title: str | None) -> str | None:
    t = _clean_title(title)
    if not t:
        return None
    if t in TITLE_SOURCE_COLLECTION:
        return TITLE_SOURCE_COLLECTION[t]
    for key, col in TITLE_SOURCE_COLLECTION.items():
        if key in t:
            return col
    return None


def _title_to_output_command(title: str | None) -> str | None:
    t = _clean_title(title)
    if not t:
        return None
    if t in TITLE_OUTPUT_COMMAND:
        return TITLE_OUTPUT_COMMAND[t]
    for key, cmd in TITLE_OUTPUT_COMMAND.items():
        if key in t:
            return cmd
    return None


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
    return "@" + str(username).lower().lstrip("@")


def source_username(message: Message) -> str | None:
    origin = getattr(message, "forward_origin", None)

    chat = getattr(origin, "chat", None) if origin else None
    username = getattr(chat, "username", None) if chat else None
    if username:
        return _normalize_username(username)

    sender_user = getattr(origin, "sender_user", None) if origin else None
    username = getattr(sender_user, "username", None) if sender_user else None
    if username:
        return _normalize_username(username)

    if message.via_bot and message.via_bot.username:
        return _normalize_username(message.via_bot.username)

    # Source bots posting directly in group.
    if message.from_user and message.from_user.is_bot and message.from_user.username:
        return _normalize_username(message.from_user.username)

    # Legacy aiogram/Telegram fields.
    fchat = getattr(message, "forward_from_chat", None)
    if fchat and getattr(fchat, "username", None):
        return _normalize_username(fchat.username)

    fuser = getattr(message, "forward_from", None)
    if fuser and getattr(fuser, "username", None):
        return _normalize_username(fuser.username)

    return None


def source_title(message: Message) -> str | None:
    origin = getattr(message, "forward_origin", None)

    chat = getattr(origin, "chat", None) if origin else None
    title = getattr(chat, "title", None) if chat else None
    if title:
        return title

    sender_user = getattr(origin, "sender_user", None) if origin else None
    if sender_user:
        full_name = getattr(sender_user, "full_name", None)
        if full_name:
            return full_name
        first_name = getattr(sender_user, "first_name", None)
        if first_name:
            return first_name

    hidden_name = getattr(origin, "sender_user_name", None) if origin else None
    if hidden_name:
        return hidden_name

    fchat = getattr(message, "forward_from_chat", None)
    if fchat and getattr(fchat, "title", None):
        return fchat.title

    fuser = getattr(message, "forward_from", None)
    if fuser:
        full_name = getattr(fuser, "full_name", None)
        if full_name:
            return full_name
        first_name = getattr(fuser, "first_name", None)
        if first_name:
            return first_name

    return None


def _custom_source_command(message: Message) -> str | None:
    uname = source_username(message)
    title = source_title(message) or ""
    text = f"{title}\n{message.caption or message.text or ''}".lower()

    if uname and uname in settings.forward_source_commands:
        return settings.forward_source_commands[uname]

    for key, cmd in settings.forward_source_commands.items():
        key_l = key.lower().strip()
        if key_l.startswith("@"):
            continue
        if "|" in key_l:
            parts = [p.strip() for p in key_l.split("|") if p.strip()]
            if all(p in text for p in parts):
                return cmd
        elif key_l and key_l in text:
            return cmd
    return None


def resolve_collection(message: Message) -> str | None:
    username = source_username(message)
    if username and username in BOT_SOURCE_COLLECTION:
        return BOT_SOURCE_COLLECTION[username]

    title_col = _title_to_collection(source_title(message))
    if title_col:
        return title_col

    custom_cmd = _custom_source_command(message)
    if custom_cmd:
        col = collection_from_command(custom_cmd)
        if col:
            return col

    cmd = command_from_text(message.caption or message.text or "")
    return collection_from_command(cmd)


def output_command_from_message(message: Message, collection: str | None = None) -> str | None:
    username = source_username(message)
    if username and username in BOT_SOURCE_OUTPUT_COMMAND:
        return BOT_SOURCE_OUTPUT_COMMAND[username]

    title_cmd = _title_to_output_command(source_title(message))
    if title_cmd:
        return title_cmd

    custom_cmd = _custom_source_command(message)
    if custom_cmd and collection_from_command(custom_cmd) == collection:
        return custom_cmd

    cmd = command_from_text(message.caption or message.text or "")
    if cmd and collection_from_command(cmd) == collection:
        return cmd

    if collection:
        return COLLECTION_TO_OUTPUT_COMMAND.get(collection)
    return None


def default_collection() -> str:
    return collection_from_command(settings.default_command) or "items_characters_hallow"


def all_lookup_collections() -> list[str]:
    return list(COLLECTION_TO_OUTPUT_COMMAND.keys())
