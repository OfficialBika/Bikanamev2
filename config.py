from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int = 0) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _csv(name: str) -> List[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def _ids(name: str) -> Set[int]:
    out: Set[int] = set()
    for x in _csv(name):
        try:
            out.add(int(x))
        except ValueError:
            pass
    return out


def _sample_points() -> Tuple[float, ...]:
    raw = _csv("VIDEO_SAMPLE_POINTS") or ["20", "50", "80"]
    pts: List[float] = []
    for x in raw:
        try:
            v = float(x)
            pts.append(max(0.0, min(1.0, v / 100.0 if v > 1 else v)))
        except ValueError:
            pass
    return tuple(pts or [0.2, 0.5, 0.8])


# Waifu Database V2 source collections.
COLLECTION_TO_OUTPUT_COMMAND: Dict[str, str] = {
    "items_character_catcher": "/catch",
    "items_characters_hallow": "/hallow",
    "items_capture_character": "/capture",
    "items_character_seizer": "/seize",
    "items_husbando_grabber": "/grab",
    "items_grab_your_waifu": "/grab",
    "items_grab_your_husbando": "/grab",
    "items_takers_character": "/take",
    "items_catch_your_husbando": "/guess",
    "items_smash_character": "/smash",
    "items_waifux_grab": "/grab",
    "items_catch_your_waifu": "/guess",
    "items_waifu_grabber": "/grab",
    "items_unknown": "/name",
}

# Best-effort direct command to collection. Shared commands like /grab and /guess are resolved by source first.
COMMAND_TO_COLLECTION: Dict[str, str] = {
    "/catch": "items_character_catcher",
    "/hallow": "items_characters_hallow",
    "/capture": "items_capture_character",
    "/seize": "items_character_seizer",
    "/loot": "items_character_seizer",
    "/take": "items_takers_character",
    "/smash": "items_smash_character",
}

BOT_SOURCE_COLLECTION: Dict[str, str] = {
    "@character_catcher_bot": "items_character_catcher",
    "@characters_hallow_bot": "items_characters_hallow",
    "@hallowuploads": "items_characters_hallow",
    "@capturecharacterbot": "items_capture_character",
    "@capturedatabase": "items_capture_character",
    "@character_seizer_bot": "items_character_seizer",
    "@seizer_database": "items_character_seizer",
    "@characterlootbot": "items_character_seizer",
    "@husbando_grabber_bot": "items_husbando_grabber",
    "@grab_your_waifu_bot": "items_grab_your_waifu",
    "@grab_your_husbando_bot": "items_grab_your_husbando",
    "@takers_character_bot": "items_takers_character",
    "@catch_your_husbando_bot": "items_catch_your_husbando",
    "@smash_character_bot": "items_smash_character",
    "@waifuxgrabbot": "items_waifux_grab",
    "@catch_your_waifu_bot": "items_catch_your_waifu",
    "@waifu_grabber_bot": "items_waifu_grabber",
}

# Some bots share a database collection but need a different command in the result.
# @CharacterLootBot uses the Seizer database collection, but users should copy /loot.
BOT_SOURCE_OUTPUT_COMMAND: Dict[str, str] = {
    "@characterlootbot": "/loot",
}

# These commands should return only the name/hint/full.
# ID and rarity are intentionally hidden for Capture, Seizer and Loot results.
HIDE_ID_RARITY_COMMANDS: Set[str] = {"/capture", "/seize", "/loot"}

SYSTEM_COLLECTIONS = {"sudo_users", "known_users", "user_modes", "settings", "items"}


def _custom_forward_source_commands() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for pair in _csv("FORWARD_SOURCE_COMMANDS"):
        if ":" not in pair:
            continue
        source, cmd = pair.split(":", 1)
        source = source.strip().lower()
        cmd = cmd.strip().lower()
        if source and cmd:
            out[source] = cmd
    return out


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    bot_username: str = os.getenv("BOT_USERNAME", "").lstrip("@")
    owner_ids: Set[int] = field(default_factory=lambda: _ids("OWNER_IDS") | _ids("OWNER_ID"))
    sudo_ids: Set[int] = field(default_factory=lambda: _ids("SUDO_IDS"))
    owner_username: str = os.getenv("OWNER_USERNAME", "@Official_Bika")

    mongo_uri: str = os.getenv("MONGO_URI", "")
    db_name: str = os.getenv("DB_NAME", "waifu_adding_v2")

    mode: str = os.getenv("MODE", "polling").lower()
    use_webhook: bool = _bool("USE_WEBHOOK", False)
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")
    webhook_path: str = os.getenv("WEBHOOK_PATH", "/webhook")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "change-me")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = _int("PORT", 8000)

    support_group_username: str = os.getenv("SUPPORT_GROUP_USERNAME", "")
    support_group_id: int = _int("SUPPORT_GROUP_ID", 0)
    force_join_channels: List[str] = field(default_factory=lambda: _csv("FORCE_JOIN_CHANNELS"))
    enable_force_join: bool = _bool("ENABLE_FORCE_JOIN", True)
    group_force_join_dm_only: bool = _bool("GROUP_FORCE_JOIN_DM_ONLY", True)
    force_join_dm_start_param: str = os.getenv("FORCE_JOIN_DM_START_PARAM", "forcejoin")
    force_join_cache_seconds: int = _int("FORCE_JOIN_CACHE_SECONDS", 259200)

    enable_gapprove: bool = _bool("ENABLE_GAPPROVE", True)
    gapprove_cache_seconds: int = _int("GAPPROVE_CACHE_SECONDS", 300)
    auto_lookup_enabled: bool = _bool("AUTO_LOOKUP_ENABLED", True)
    auto_lookup_only_approved_groups: bool = _bool("AUTO_LOOKUP_ONLY_APPROVED_GROUPS", True)
    auto_lookup_in_support_group: bool = _bool("AUTO_LOOKUP_IN_SUPPORT_GROUP", True)
    auto_lookup_in_dm: bool = _bool("AUTO_LOOKUP_IN_DM", False)

    default_command: str = os.getenv("DEFAULT_COMMAND", "/hallow")
    show_source_in_result: bool = _bool("SHOW_SOURCE_IN_RESULT", False)
    enable_copy_buttons: bool = _bool("ENABLE_COPY_BUTTONS", True)
    fast_reply_mode: bool = _bool("FAST_REPLY_MODE", False)

    snapshot_refresh_seconds: int = _int("SNAPSHOT_REFRESH_SECONDS", 60)
    snapshot_startup_load: bool = _bool("SNAPSHOT_STARTUP_LOAD", True)
    snapshot_background_refresh: bool = _bool("SNAPSHOT_BACKGROUND_REFRESH", True)
    result_cache_max_items: int = _int("RESULT_CACHE_MAX_ITEMS", 5000)
    result_cache_ttl_seconds: int = _int("RESULT_CACHE_TTL_SECONDS", 600)
    miss_cache_ttl_seconds: int = _int("MISS_CACHE_TTL_SECONDS", 60)

    photo_phash_threshold: int = _int("PHOTO_PHASH_THRESHOLD", 8)
    video_frame_threshold: int = _int("VIDEO_FRAME_THRESHOLD", 10)
    video_avg_threshold: int = _int("VIDEO_AVG_THRESHOLD", 12)
    video_sample_points: Tuple[float, ...] = field(default_factory=_sample_points)

    max_concurrent_downloads: int = _int("MAX_CONCURRENT_DOWNLOADS", 20)
    max_concurrent_lookups: int = _int("MAX_CONCURRENT_LOOKUPS", 50)
    download_timeout_seconds: int = _int("DOWNLOAD_TIMEOUT_SECONDS", 8)

    forward_source_commands: Dict[str, str] = field(default_factory=_custom_forward_source_commands)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    tz: str = os.getenv("TZ", "Asia/Yangon")


settings = Settings()
