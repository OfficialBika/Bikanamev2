from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from services.snapshot_cache import snapshot
from utils.perf import perf
from utils.telegram_safe import safe_reply

router = Router(name="status")


@router.message(Command("status", "stats"))
async def status(message: Message) -> None:
    p = perf.snapshot()
    text = (
        "✅ <b>Waifu Name Bot V2</b>\n"
        f"Snapshot items: <code>{snapshot.count}</code>\n"
        f"Snapshot age: <code>{snapshot.age_seconds()}s</code>\n"
        f"Lookups: <code>{p['lookup_total']}</code>\n"
        f"Hits: <code>{p['lookup_hits']}</code> | Misses: <code>{p['lookup_misses']}</code> | Errors: <code>{p['lookup_errors']}</code>\n"
        f"EMA latency: <code>{p['lookup_ema_ms']} ms</code>"
    )
    await safe_reply(message, text)
