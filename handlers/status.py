from __future__ import annotations

import logging
import time
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from database.mongo import get_db
from services.group_access import is_owner_or_sudo
from services.snapshot_cache import snapshot
from services.lookup_service import lookup_service
from utils.perf import perf
from utils.telegram_safe import safe_reply

router = Router(name="status")
log = logging.getLogger(__name__)

START_TIME = time.time()


SUPPORTED_BOTS = [
    ("@Character_Catcher_Bot", "/catch"),
    ("@Characters_Hallow_bot", "/hallow"),
    ("@CaptureCharacterBot", "/capture"),
    ("@Character_Seizer_Bot", "/seize"),
    ("@Husbando_Grabber_Bot", "/grab"),
    ("@Grab_Your_Waifu_Bot", "/grab"),
    ("@Grab_Your_Husbando_Bot", "/grab"),
    ("@Takers_character_bot", "/take"),
    ("@Catch_Your_Husbando_Bot", "/guess"),
    ("@Smash_Character_Bot", "/smash"),
    ("@WaifuxGrabBot", "/grab"),
    ("@Catch_Your_Waifu_Bot", "/guess"),
    ("@Waifu_Grabber_Bot", "/grab"),
    ("@CharacterLootBot", "/loot"),
]


def _fmt_int(n: int | None) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"


def _fmt_ms(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.0f} ms"


def _uptime() -> str:
    sec = int(time.time() - START_TIME)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _snapshot_total() -> int:
    try:
        return int(getattr(snapshot, "count"))
    except Exception:
        pass

    try:
        return len(snapshot.file_uid)
    except Exception:
        pass

    total = 0
    for attr in ("photos_by_collection", "videos_by_collection"):
        try:
            source = getattr(snapshot, attr, {}) or {}
            for items in source.values():
                total += len(items)
        except Exception:
            pass
    return total


def _snapshot_age() -> str:
    try:
        age = snapshot.age_seconds()
        return f"{int(age)}s"
    except Exception:
        pass

    for attr in ("last_refresh_at", "last_loaded_at", "loaded_at", "refreshed_at"):
        try:
            ts = getattr(snapshot, attr, None)
            if ts:
                age = int(time.time() - float(ts))
                if age < 60:
                    return f"{age}s"
                if age < 3600:
                    return f"{age // 60}m {age % 60}s"
                return f"{age // 3600}h {(age % 3600) // 60}m"
        except Exception:
            pass
    return "N/A"


def _cache_status() -> str:
    try:
        cur = len(lookup_service.result_cache)
    except Exception:
        cur = 0
    try:
        max_items = settings.result_cache_max_items
    except Exception:
        max_items = 0
    return f"{cur} / {max_items}"


def _ema_latency() -> str:
    try:
        p = perf.snapshot()
        v = p.get("lookup_ema_ms")
        if v is not None:
            return _fmt_ms(float(v))
    except Exception:
        pass

    for path in (("lookup", "ema_ms"), ("lookup", "ema"), ("lookup", "avg_ms")):
        try:
            obj = perf
            for p in path:
                obj = getattr(obj, p)
            if obj is not None:
                return _fmt_ms(float(obj))
        except Exception:
            pass
    return "N/A"


async def _count_collection(name: str) -> int:
    try:
        db = get_db()
        return await db[name].count_documents({})
    except Exception:
        return 0


async def _count_gapproved() -> int:
    try:
        db = get_db()
        return await db["settings"].count_documents({"key": {"$regex": r"^gapprove:"}, "enabled": True})
    except Exception:
        return 0


async def _db_ping_ms() -> float | None:
    try:
        db = get_db()
        t0 = time.perf_counter()
        await db.command("ping")
        return (time.perf_counter() - t0) * 1000
    except Exception:
        log.exception("db ping failed")
        return None


async def _bot_ping_ms(message: Message) -> float | None:
    try:
        t0 = time.perf_counter()
        await message.bot.get_me()
        return (time.perf_counter() - t0) * 1000
    except Exception:
        log.exception("bot ping failed")
        return None


def _ram_info() -> tuple[str, str, str]:
    try:
        data = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    data[parts[0].rstrip(":")] = int(parts[1]) * 1024

        total = data.get("MemTotal", 0)
        available = data.get("MemAvailable", 0)
        used = max(total - available, 0)

        def gb(x: int) -> str:
            return f"{x / (1024 ** 3):.2f} GB"

        return gb(used), gb(available), gb(total)
    except Exception:
        return "N/A", "N/A", "N/A"


async def build_status_text() -> str:
    known_users = await _count_collection("known_users")
    known_groups = await _count_collection("known_groups")
    gapproved = await _count_gapproved()
    blacklisted = await _count_collection("blacklisted_users")

    supported_lines = []
    for i, (username, cmd) in enumerate(SUPPORTED_BOTS, start=1):
        supported_lines.append(f"{i}. {username} : {cmd}")

    return (
        "♻ <b>BOT DATABASE STATUS</b>\n"
        f"‣ Total Media : <code>{_fmt_int(_snapshot_total())}</code>\n"
        f"‣ Known Users : <code>{_fmt_int(known_users)}</code>\n"
        f"‣ Known Groups : <code>{_fmt_int(known_groups)}</code>\n"
        f"‣ GApproved Groups : <code>{_fmt_int(gapproved)}</code>\n"
        f"‣ Blacklisted Users : <code>{_fmt_int(blacklisted)}</code>\n\n"
        "⚡ <b>LOOKUP ENGINE</b>\n"
        f"‣ Snapshot Age : <code>{_snapshot_age()}</code>\n"
        f"‣ Result Cache : <code>{_cache_status()}</code>\n"
        f"‣ EMA latency : <code>{_ema_latency()}</code>\n\n"
        "🤖 <b>Supported Bot List</b>\n"
        + "\n".join(supported_lines)
    )


async def build_stats_text(message: Message) -> str:
    db_ping = await _db_ping_ms()
    bot_ping = await _bot_ping_ms(message)
    ram_used, ram_left, ram_total = _ram_info()

    return (
        "📊 <b>OWNER BOT STATS</b>\n\n"
        f"‣ Uptime : <code>{_uptime()}</code>\n"
        f"‣ DB Ping : <code>{_fmt_ms(db_ping)}</code>\n"
        f"‣ Bot Ping : <code>{_fmt_ms(bot_ping)}</code>\n"
        f"‣ RAM Used : <code>{ram_used}</code>\n"
        f"‣ RAM Left : <code>{ram_left}</code>\n"
        f"‣ RAM Total : <code>{ram_total}</code>\n\n"
        "⚡ <b>LOOKUP ENGINE</b>\n"
        f"‣ Snapshot Age : <code>{_snapshot_age()}</code>\n"
        f"‣ Total Media : <code>{_fmt_int(_snapshot_total())}</code>\n"
        f"‣ Result Cache : <code>{_cache_status()}</code>\n"
        f"‣ EMA latency : <code>{_ema_latency()}</code>"
    )


@router.message(Command("status"))
async def status_cmd(message: Message) -> None:
    await safe_reply(message, await build_status_text())


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not is_owner_or_sudo(user_id):
        await safe_reply(message, "❌ Owner only command.")
        return

    await safe_reply(message, await build_stats_text(message))
