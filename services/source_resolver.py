from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from aiogram.types import Message

from config import (
    BOT_SOURCE_CHAT_ID,
    BOT_SOURCE_COLLECTION,
    BOT_SOURCE_USER_ID,
    BOT_SOURCE_OUTPUT_COMMAND,
    BOT_SOURCE_OUTPUT_USER_ID,
    COLLECTION_TO_OUTPUT_COMMAND,
    COMMAND_TO_COLLECTION,
    settings,
)

try:
    from services.source_blocker import is_blocked_source  # type: ignore
except Exception:  # pragma: no cover
    def is_blocked_source(message: Message | None) -> bool:  # type: ignore
        return False


@dataclass(frozen=True)
class LookupScope:
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
    "items_senpai_catcher",
    "items_super_zeko",
    "items_orinx_waifu",
]

COMMAND_TO_COLLECTIONS: dict[str, list[str]] = {
    "/catch": ["items_character_catcher"],
    "/hallow": ["items_characters_hallow"],
    "/capture": ["items_capture_character"],
    "/seize": ["items_character_seizer"],
    "/loot": ["items_capture_character"],
    "/take": ["items_takers_character"],
    "/smash": ["items_smash_character"],
    "/challenge": ["items_roronoa_zoro"],
    "/bika": ["items_bika_character"],
    "/ziceko": ["items_super_zeko"],
    "/orin": ["items_orinx_waifu"],
    "/pick": ["items_character_picker", "items_senpai_catcher"],
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
    "𝑶": "o", "𝒓": "r", "𝒊": "i", "𝒏": "n", "𝑿": "x", "𝑾": "w", "𝒂": "a", "𝒇": "f", "𝒖": "u", "𝑩": "b", "𝒐": "o", "𝒕": "t",
})


def _norm_text(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").translate(STYLIZED_LATIN_TRANSLATION)


def _clean_title(s: str | None) -> str:
    if not s:
        return ""
    s = _norm_text(s).lower().strip().replace("_", " ")
    s = s.replace("「", " ").replace("」", " ")
    s = re.sub(r"[^0-9a-z\u1000-\u109f\s]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


TITLE_SOURCE_COLLECTION: dict[str, str] = {
    # Character Catcher / Hallow / Capture / Seizer / Loot
    "character catcher": "items_character_catcher",
    "character catcher bot": "items_character_catcher",
    "characters hallow": "items_characters_hallow",
    "characters hallow bot": "items_characters_hallow",
    "character hallow": "items_characters_hallow",
    "hallow upload": "items_characters_hallow",
    "hallow uploads": "items_characters_hallow",
    "capture character": "items_capture_character",
    "capture database": "items_capture_character",
    "character loot": "items_capture_character",
    "character loot bot": "items_capture_character",
    "character seizer": "items_character_seizer",
    "character seizer bot": "items_character_seizer",
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
    "waifuxgrab db": "items_waifux_grab",
    "grab garden": "items_waifux_grab",
    "waifu grabber": "items_waifu_grabber",
    "waifu grabber bot": "items_waifu_grabber",
    # Guess family / other sources
    "takers character": "items_takers_character",
    "takers character bot": "items_takers_character",
    "catch your husbando": "items_catch_your_husbando",
    "catch your husbando bot": "items_catch_your_husbando",
    "catch your waifu": "items_catch_your_waifu",
    "catch your waifu bot": "items_catch_your_waifu",
    "smash character": "items_smash_character",
    "smash character bot": "items_smash_character",
    "roronoa zoro": "items_roronoa_zoro",
    "roronoa zoro bot": "items_roronoa_zoro",
    "character picker": "items_character_picker",
    "character picker bot": "items_character_picker",
    "picker bot": "items_character_picker",
    "bika waifu database": "items_bika_character",
    "bika character bot": "items_bika_character",
    "senpai catcher": "items_senpai_catcher",
    "senpai catcher bot": "items_senpai_catcher",
    "senpaicatcher": "items_senpai_catcher",
    "senpai base": "items_senpai_catcher",
    "senpaibase": "items_senpai_catcher",
    # New sources
    "myanmar character": "items_super_zeko",
    "myanmar character logs": "items_super_zeko",
    "super zeko": "items_super_zeko",
    "super zeko bot": "items_super_zeko",
    "ziceko data": "items_super_zeko",
    "zicekodata 1": "items_super_zeko",
    "orinx waifu": "items_orinx_waifu",
    "orinx waifu bot": "items_orinx_waifu",
    "orinx catcher waifu bot": "items_orinx_waifu",
    "timunagalaya": "items_orinx_waifu",
}

TITLE_OUTPUT_COMMAND: dict[str, str] = {
    "character loot": "/loot",
    "character loot bot": "/loot",
    "roronoa zoro": "/challenge",
    "roronoa zoro bot": "/challenge",
    "character picker": "/pick",
    "character picker bot": "/pick",
    "picker bot": "/pick",
    "bika waifu database": "/bika",
    "bika character bot": "/bika",
    "senpai catcher": "/pick",
    "senpai catcher bot": "/pick",
    "senpaicatcher": "/pick",
    "senpaibase": "/pick",
    "myanmar character": "/ziceko",
    "myanmar character logs": "/ziceko",
    "super zeko": "/ziceko",
    "zicekodata 1": "/ziceko",
    "orinx waifu": "/orin",
    "orinx waifu bot": "/orin",
    "orinx catcher waifu bot": "/orin",
    "timunagalaya": "/orin",
}

CONTENT_SOURCE_RULES: list[tuple[re.Pattern[str], str, str | None]] = [
    # WaifuxGrab DB captions. This fixes cases where Telegram hides the forward username/title.
    (re.compile(r"new\s+waifu\s+added|item\s*id\s*[:：].*\bname\b\s*[:：].*\brarity\b\s*[:：]|waifuxgrab", re.I | re.S), "items_waifux_grab", "/grab"),
    # Senpai DB captions.
    (re.compile(r"new\s+character\s+added\s+to\s+the\s+bot|char\s*id\s*[:：].*\bname\b\s*[:：].*\banime\b\s*[:：].*\brarity\b\s*[:：]", re.I | re.S), "items_senpai_catcher", "/pick"),
    # OrinX DB captions.
    (re.compile(r"character\s+database.*\bid\b\s*[:：].*\bname\b\s*[:：].*\bseries\b\s*[:：].*\brarity\b\s*[:：].*\bexported\b", re.I | re.S), "items_orinx_waifu", "/orin"),
    # Super Zeko / Myanmar Character logs.
    (re.compile(r"card\s+drop|myanmar\s+character|/ziceko|တင်ပြီးပြီ|uploaded\s*\(/?li\)|📛.*name|⭐.*rarity", re.I | re.S), "items_super_zeko", "/ziceko"),
]


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
    # Some Telegram clients put forwarded preview text in external_reply/reply_to_message.
    for obj in (getattr(message, "external_reply", None), getattr(message, "reply_to_message", None)):
        if obj is not None:
            parts.extend([
                getattr(obj, "caption", None),
                getattr(obj, "text", None),
                getattr(obj, "html_text", None),
                getattr(obj, "md_text", None),
            ])
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
            return None
    return None


def source_user_id(message: Message) -> int | None:
    """Return forwarded/via/sender bot user id when Telegram exposes it.

    Forwarded bot media can show only the display name in the client (for example
    "Grab Garden") while the Bot API still exposes forward_origin.sender_user.id.
    User-id mapping is the strongest way to route those messages to the exact
    source collection.
    """
    origin = getattr(message, "forward_origin", None)
    sender_user = getattr(origin, "sender_user", None) if origin else None
    for user in (
        sender_user,
        getattr(message, "via_bot", None),
        getattr(message, "forward_from", None),
        getattr(message, "from_user", None) if getattr(getattr(message, "from_user", None), "is_bot", False) else None,
    ):
        if user and getattr(user, "id", None) is not None:
            try:
                return int(user.id)
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
            return str(full_name)

    hidden_name = getattr(origin, "sender_user_name", None) if origin else None
    if hidden_name:
        return str(hidden_name)

    fuser = getattr(message, "forward_from", None)
    if fuser:
        full_name = getattr(fuser, "full_name", None) or getattr(fuser, "first_name", None)
        if full_name:
            return str(full_name)
    return None


def _content_source(message: Message) -> tuple[str | None, str | None]:
    text = _message_text(message)
    if not text:
        return None, None
    for pattern, collection, cmd in CONTENT_SOURCE_RULES:
        if pattern.search(text):
            return collection, cmd
    return None, None


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
    if is_blocked_source(message):
        return None

    username = source_username(message)
    if username and username in BOT_SOURCE_COLLECTION:
        return BOT_SOURCE_COLLECTION[username]

    user_id = source_user_id(message)
    if user_id is not None and int(user_id) in BOT_SOURCE_USER_ID:
        return BOT_SOURCE_USER_ID[int(user_id)]

    chat_id = source_chat_id(message)
    if chat_id is not None and int(chat_id) in BOT_SOURCE_CHAT_ID:
        return BOT_SOURCE_CHAT_ID[int(chat_id)]

    title_col = _title_to_collection(source_title(message))
    if title_col:
        return title_col

    content_col, _ = _content_source(message)
    if content_col:
        return content_col

    custom_cmd = _custom_source_command(message)
    if custom_cmd:
        cols = collections_from_command(custom_cmd)
        if len(cols) == 1:
            return cols[0]
    return None


def resolve_lookup_scope(message: Message) -> LookupScope:
    if is_blocked_source(message):
        return LookupScope(collections=[], mode="blocked", command=None, strict=True, confident=True, source_label=source_username(message) or source_title(message))

    source_col = resolve_source_collection(message)
    cmd = command_from_text(_message_text(message))
    content_col, content_cmd = _content_source(message)
    if not cmd and content_cmd:
        cmd = content_cmd
    label = source_username(message) or source_title(message)

    if source_col:
        return LookupScope(
            collections=[source_col],
            mode="source",
            command=cmd or COLLECTION_TO_OUTPUT_COMMAND.get(source_col),
            source_collection=source_col,
            strict=settings.strict_forward_source_lookup,
            confident=True,
            source_label=label,
        )

    cmd_cols = collections_from_command(cmd)
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
    return cols[0] if cols and len(cols) == 1 else None


def output_command_from_message(message: Message, collection: str | None = None) -> str | None:
    username = source_username(message)
    if username and username in BOT_SOURCE_OUTPUT_COMMAND:
        return BOT_SOURCE_OUTPUT_COMMAND[username]

    user_id = source_user_id(message)
    if user_id is not None and int(user_id) in BOT_SOURCE_OUTPUT_USER_ID:
        return BOT_SOURCE_OUTPUT_USER_ID[int(user_id)]

    title_cmd = _title_to_output_command(source_title(message))
    if title_cmd:
        return title_cmd

    _, content_cmd = _content_source(message)
    if content_cmd:
        cols = collections_from_command(content_cmd)
        if not collection or collection in cols:
            return content_cmd

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
