from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from aiogram.types import Message
from config import (
    BOT_SOURCE_COLLECTION,
    BOT_SOURCE_OUTPUT_COMMAND,
    COLLECTION_TO_OUTPUT_COMMAND,
    COMMAND_TO_COLLECTION,
    settings,
)

# Optional in newer config.py. Keep backward compatible with old config files.
try:
    from config import BOT_SOURCE_CHAT_ID  # type: ignore
except Exception:  # pragma: no cover
    BOT_SOURCE_CHAT_ID = {}

# Optional blocked-source guard. Keep this lazy/backward compatible so this file
# still works before services/source_blocker.py is copied into the repo.
try:
    from services.source_blocker import is_blocked_source  # type: ignore
except Exception:  # pragma: no cover
    def is_blocked_source(message: Message | None) -> bool:  # type: ignore
        return False

# Manual lookup commands. /loop is intentionally NOT included.
MANUAL_COMMANDS = {"/waifu", "/w", ".wa", ".w", "/name", ".name", "/bika", "/loot", "/pick"}


@dataclass(frozen=True)
class LookupScope:
    """Resolved lookup scope for fast source/command-aware search.

    Priority required by owner:
      1) Bot/source username or title/chat id -> exact source collection
      2) If source is unknown, use command inside forwarded caption/text -> command collection(s)
      3) If still unknown, no scope. lookup_service returns Not Found when REQUIRE_LOOKUP_SCOPE=true.
    """

    collections: list[str] | None
    mode: str
    command: str | None = None
    source_collection: str | None = None
    strict: bool = False
    confident: bool = False
    source_label: str | None = None


USING_RE = re.compile(r"(?:using|use|hint|full|cmd|command)\s*[:：\-=]?\s*(/[a-zA-Z0-9_]+)(?:@[A-Za-z0-9_]+)?", re.I)
CMD_RE = re.compile(r"(^|\s)(/[a-zA-Z0-9_]+)(?:@[A-Za-z0-9_]+)?(?=\s|$|[^A-Za-z0-9_@])", re.I)

LOOKUP_COLLECTION_ORDER: list[str] = [
    "items_character_catcher",
    "items_characters_hallow",
    "items_capture_character",
    "items_character_seizer",
    "items_husbando_grabber",
    "items_grab_your_waifu",
    "items_grab_your_husbando",
    "items_takers_character",
    "items_catch_your_husbando",
    "items_smash_character",
    "items_waifux_grab",
    "items_catch_your_waifu",
    "items_waifu_grabber",
    "items_roronoa_zoro",
    "items_character_picker",
    "items_bika_character",
    "items_super_zeko",
    "items_senpai_catcher",
]

# Commands that may map to more than one collection. Source has priority over these groups.
COMMAND_TO_COLLECTIONS: dict[str, list[str]] = {
    "/catch": ["items_character_catcher"],
    "/hallow": ["items_characters_hallow"],
    "/capture": ["items_capture_character"],
    "/seize": ["items_character_seizer"],
    "/loot": ["items_capture_character"],
    "/take": ["items_takers_character"],
    "/smash": ["items_smash_character"],
    "/challenge": ["items_roronoa_zoro"],
    "/pick": ["items_character_picker", "items_senpai_catcher"],
    "/ziceko": ["items_super_zeko"],
    "/bika": ["items_bika_character"],
    "/grab": [
        "items_husbando_grabber",
        "items_grab_your_waifu",
        "items_grab_your_husbando",
        "items_waifux_grab",
        "items_waifu_grabber",
    ],
    "/guess": ["items_catch_your_husbando", "items_catch_your_waifu"],
}

STYLIZED_LATIN_TRANSLATION = str.maketrans({
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ꜰ": "f",
    "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l",
    "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ʀ": "r", "ꜱ": "s",
    "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ʏ": "y", "ᴢ": "z",
})


def _norm_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(STYLIZED_LATIN_TRANSLATION)
    return value


TITLE_SOURCE_COLLECTION = {
    # Character Catcher
    "character catcher": "items_character_catcher",
    "character catcher bot": "items_character_catcher",
    "characters catcher": "items_character_catcher",
    "characters catcher bot": "items_character_catcher",

    # Myanmar Character / Super Zeko
    "myanmar character": "items_super_zeko",
    "myanmar character bot": "items_super_zeko",
    "myanmar character logs": "items_super_zeko",
    "super zeko": "items_super_zeko",
    "super zeko bot": "items_super_zeko",
    "ziceko data": "items_super_zeko",
    "zicekodata 1": "items_super_zeko",

    # Hallow
    "character hallow": "items_characters_hallow",
    "character hallow bot": "items_characters_hallow",
    "characters hallow": "items_characters_hallow",
    "characters hallow bot": "items_characters_hallow",
    "hallow upload": "items_characters_hallow",
    "hallow uploads": "items_characters_hallow",

    # Capture / Loot
    "capture character": "items_capture_character",
    "character capture": "items_capture_character",
    "character capture bot": "items_capture_character",
    "capture database": "items_capture_character",
    "character loot": "items_capture_character",
    "character loot bot": "items_capture_character",
    "character looter": "items_capture_character",
    "character looter bot": "items_capture_character",

    # Seizer
    "character seizer": "items_character_seizer",
    "character seizer bot": "items_character_seizer",
    "character seize": "items_character_seizer",
    "character seize bot": "items_character_seizer",
    "seizer database": "items_character_seizer",

    # Grab family
    "husbando grabber": "items_husbando_grabber",
    "husbando grabber bot": "items_husbando_grabber",
    "grab your waifu": "items_grab_your_waifu",
    "grab your waifu bot": "items_grab_your_waifu",
    "grab your husbando": "items_grab_your_husbando",
    "grab your husbando bot": "items_grab_your_husbando",
    "waifuxgrab": "items_waifux_grab",
    "waifux grab": "items_waifux_grab",
    "waifuxgrab database": "items_waifux_grab",
    "waifuxgrab_database": "items_waifux_grab",
    "waifuxgrab db": "items_waifux_grab",
    "grab garden": "items_waifux_grab",
    "waifu grabber": "items_waifu_grabber",
    "waifu grabber bot": "items_waifu_grabber",

    # Others
    "takers bot": "items_takers_character",
    "takers character": "items_takers_character",
    "takers character bot": "items_takers_character",
    "catch your husbando": "items_catch_your_husbando",
    "catch your husbando bot": "items_catch_your_husbando",
    "catch your waifu": "items_catch_your_waifu",
    "catch your waifu bot": "items_catch_your_waifu",
    "smash your character": "items_smash_character",
    "smash your character bot": "items_smash_character",
    "smash character": "items_smash_character",
    "smash character bot": "items_smash_character",
    "roronoa zoro": "items_roronoa_zoro",
    "roronoa zoro bot": "items_roronoa_zoro",
    "picker bot": "items_character_picker",
    "character picker": "items_character_picker",
    "character picker bot": "items_character_picker",
    "bika waifu database": "items_bika_character",
    "bika character bot": "items_bika_character",
    "senpai catcher": "items_senpai_catcher",
    "senpai catcher bot": "items_senpai_catcher",
    "senpaicatcher": "items_senpai_catcher",
    "senpaicatcher db": "items_senpai_catcher",
    "senpaicatcher database": "items_senpai_catcher",
    "senpaibase": "items_senpai_catcher",
}

TITLE_OUTPUT_COMMAND = {
    "myanmar character": "/ziceko",
    "myanmar character bot": "/ziceko",
    "myanmar character logs": "/ziceko",
    "super zeko": "/ziceko",
    "super zeko bot": "/ziceko",
    "zicekodata 1": "/ziceko",
    "character loot": "/loot",
    "character loot bot": "/loot",
    "character looter": "/loot",
    "character looter bot": "/loot",
    "roronoa zoro": "/challenge",
    "roronoa zoro bot": "/challenge",
    "picker bot": "/pick",
    "character picker": "/pick",
    "character picker bot": "/pick",
    "bika waifu database": "/bika",
    "bika character bot": "/bika",
    "senpai catcher": "/pick",
    "senpai catcher bot": "/pick",
    "senpaicatcher": "/pick",
    "senpaicatcher db": "/pick",
    "senpaibase": "/pick",
}


def _clean_title(s: str | None) -> str:
    if not s:
        return ""
    s = _norm_text(s).lower().strip().replace("_", " ")
    s = s.replace("「", " ").replace("」", " ")
    s = re.sub(r"[^0-9a-z\u1000-\u109f\s]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _title_to_collection(title: str | None) -> str | None:
    t = _clean_title(title)
    if not t:
        return None
    if t in TITLE_SOURCE_COLLECTION:
        return TITLE_SOURCE_COLLECTION[t]
    for key, col in TITLE_SOURCE_COLLECTION.items():
        if key in t or t in key:
            return col
    return None


def _title_to_output_command(title: str | None) -> str | None:
    t = _clean_title(title)
    if not t:
        return None
    if t in TITLE_OUTPUT_COMMAND:
        return TITLE_OUTPUT_COMMAND[t]
    for key, cmd in TITLE_OUTPUT_COMMAND.items():
        if key in t or t in key:
            return cmd
    return None


def _message_text(message: Message) -> str:
    parts = [
        getattr(message, "caption", None),
        getattr(message, "text", None),
        getattr(message, "html_text", None),
        getattr(message, "md_text", None),
    ]
    return "\n".join(_norm_text(p) for p in parts if isinstance(p, str) and p.strip())


def command_from_text(text: str | None) -> str | None:
    if not text:
        return None
    t = _norm_text(text).strip()
    first = t.split(maxsplit=1)[0].lower() if t else ""
    first = first.split("@", 1)[0]
    if first in COMMAND_TO_COLLECTIONS or first in COMMAND_TO_COLLECTION:
        return first
    m = USING_RE.search(t) or CMD_RE.search(t)
    if m:
        cmd = m.group(m.lastindex or 1).lower().split("@", 1)[0]
        if cmd in COMMAND_TO_COLLECTIONS or cmd in COMMAND_TO_COLLECTION:
            return cmd
    return None


def collections_from_command(cmd: str | None) -> list[str]:
    if not cmd:
        return []
    cmd = cmd.lower().split("@", 1)[0]
    if cmd in COMMAND_TO_COLLECTIONS:
        return list(COMMAND_TO_COLLECTIONS[cmd])
    col = COMMAND_TO_COLLECTION.get(cmd)
    return [col] if col else []


def collection_from_command(cmd: str | None) -> str | None:
    cols = collections_from_command(cmd)
    return cols[0] if cols else None


def _normalize_username(username: str | None) -> str | None:
    username = (username or "").strip().lower().lstrip("@")
    return f"@{username}" if username else None


def _source_origin_chat(message: Message):
    origin = getattr(message, "forward_origin", None)
    if origin:
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if chat:
            return chat
    legacy = getattr(message, "forward_from_chat", None)
    if legacy:
        return legacy
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat:
        return sender_chat
    return None


def source_chat_id(message: Message) -> int | None:
    chat = _source_origin_chat(message)
    if chat and getattr(chat, "id", None) is not None:
        try:
            return int(chat.id)
        except Exception:
            pass
    return None


def source_username(message: Message) -> str | None:
    chat = _source_origin_chat(message)
    if chat and getattr(chat, "username", None):
        return _normalize_username(chat.username)

    origin = getattr(message, "forward_origin", None)
    sender_user = getattr(origin, "sender_user", None) if origin else None
    if sender_user and getattr(sender_user, "username", None):
        return _normalize_username(sender_user.username)

    if getattr(message, "via_bot", None) and message.via_bot.username:
        return _normalize_username(message.via_bot.username)

    if message.from_user and message.from_user.is_bot and message.from_user.username:
        return _normalize_username(message.from_user.username)

    fuser = getattr(message, "forward_from", None)
    if fuser and getattr(fuser, "username", None):
        return _normalize_username(fuser.username)

    return None


def source_title(message: Message) -> str | None:
    chat = _source_origin_chat(message)
    if chat and getattr(chat, "title", None):
        return str(chat.title)

    origin = getattr(message, "forward_origin", None)
    sender_user = getattr(origin, "sender_user", None) if origin else None
    if sender_user:
        full_name = getattr(sender_user, "full_name", None) or " ".join(
            x for x in [getattr(sender_user, "first_name", None), getattr(sender_user, "last_name", None)] if x
        )
        if full_name:
            return full_name

    hidden_name = getattr(origin, "sender_user_name", None) if origin else None
    if hidden_name:
        return str(hidden_name)

    fuser = getattr(message, "forward_from", None)
    if fuser:
        full_name = getattr(fuser, "full_name", None) or getattr(fuser, "first_name", None)
        if full_name:
            return str(full_name)
    return None


def _custom_source_command(message: Message) -> str | None:
    uname = source_username(message)
    title = source_title(message) or ""
    text = f"{title}\n{_message_text(message)}".lower()

    if uname and uname in settings.forward_source_commands:
        return settings.forward_source_commands[uname]

    for key, cmd in settings.forward_source_commands.items():
        key_l = key.lower().strip()
        if key_l.startswith("@"):
            continue
        if "|" in key_l:
            parts = [p.strip() for p in key_l.split("|") if p.strip()]
            if parts and all(p in text for p in parts):
                return cmd
        elif key_l and key_l in text:
            return cmd
    return None


def resolve_source_collection(message: Message) -> str | None:
    """Resolve collection from source only: bot username, channel username, title, or chat id.

    This intentionally does not use the caption command. If this returns None,
    resolve_lookup_scope() will then use the command inside the forwarded caption/text.
    """
    if is_blocked_source(message):
        return None

    username = source_username(message)
    if username and username in BOT_SOURCE_COLLECTION:
        return BOT_SOURCE_COLLECTION[username]

    chat_id = source_chat_id(message)
    if chat_id is not None and int(chat_id) in BOT_SOURCE_CHAT_ID:
        return BOT_SOURCE_CHAT_ID[int(chat_id)]

    title_col = _title_to_collection(source_title(message))
    if title_col:
        return title_col

    custom_cmd = _custom_source_command(message)
    if custom_cmd:
        cols = collections_from_command(custom_cmd)
        if len(cols) == 1:
            return cols[0]
    return None


def resolve_lookup_scope(message: Message) -> LookupScope:
    """Resolve the narrowest safe lookup scope.

    Owner requested auto lookup logic:
    - Blocked source bots/channels return mode="blocked" and must not be searched.
    - First check bot/channel name + username.
    - If not found, read command in forwarded caption/text and search only that command's collection(s).
    """
    if is_blocked_source(message):
        return LookupScope(
            collections=[],
            mode="blocked",
            command=None,
            source_collection=None,
            strict=True,
            confident=True,
            source_label=source_username(message) or source_title(message),
        )

    source_col = resolve_source_collection(message)
    cmd = command_from_text(_message_text(message))
    cmd_cols = collections_from_command(cmd)
    label = source_username(message) or source_title(message)

    if source_col:
        return LookupScope(
            collections=[source_col],
            mode="source",
            command=cmd,
            source_collection=source_col,
            strict=settings.strict_forward_source_lookup,
            confident=True,
            source_label=label,
        )

    if cmd_cols:
        return LookupScope(
            collections=cmd_cols,
            mode="command",
            command=cmd,
            source_collection=None,
            strict=settings.strict_command_lookup,
            confident=True,
            source_label=label,
        )

    return LookupScope(collections=None, mode="all", command=cmd, strict=False, confident=False, source_label=label)


def resolve_lookup_collections(message: Message) -> list[str] | None:
    return resolve_lookup_scope(message).collections


def resolve_collection(message: Message) -> str | None:
    cols = resolve_lookup_collections(message)
    if cols and len(cols) == 1:
        return cols[0]
    return None


def output_command_from_message(message: Message, collection: str | None = None) -> str | None:
    username = source_username(message)
    if username and username in BOT_SOURCE_OUTPUT_COMMAND:
        return BOT_SOURCE_OUTPUT_COMMAND[username]

    title_cmd = _title_to_output_command(source_title(message))
    if title_cmd:
        return title_cmd

    custom_cmd = _custom_source_command(message)
    if custom_cmd:
        cols = collections_from_command(custom_cmd)
        if not collection or collection in cols:
            return custom_cmd

    cmd = command_from_text(_message_text(message))
    if cmd:
        cols = collections_from_command(cmd)
        if not collection or collection in cols:
            return cmd

    if collection:
        return COLLECTION_TO_OUTPUT_COMMAND.get(collection)
    return None


def default_collection() -> str:
    return collection_from_command(settings.default_command) or "items_characters_hallow"


def all_lookup_collections() -> list[str]:
    return [c for c in LOOKUP_COLLECTION_ORDER if c in COLLECTION_TO_OUTPUT_COMMAND]
