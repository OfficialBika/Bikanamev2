from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import settings
from database.indexes import ensure_indexes
from database.mongo import close_mongo, init_mongo
from handlers import admin, auto_lookup, manual_lookup, start, status
from services.snapshot_cache import snapshot

try:
    import uvloop
except Exception:  # pragma: no cover
    uvloop = None


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(status.router)
    dp.include_router(manual_lookup.router)
    dp.include_router(auto_lookup.router)
    return dp


async def on_startup(bot: Bot) -> None:
    await init_mongo()
    await ensure_indexes()
    if settings.snapshot_startup_load:
        await snapshot.refresh()
    if settings.snapshot_background_refresh:
        asyncio.create_task(snapshot.refresh_loop())
    if settings.use_webhook or settings.mode == "webhook":
        if not settings.public_url:
            raise RuntimeError("PUBLIC_URL is required for webhook mode")
        await bot.set_webhook(
            settings.public_url + settings.webhook_path,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
        )


async def on_shutdown(bot: Bot) -> None:
    if settings.use_webhook or settings.mode == "webhook":
        await bot.delete_webhook(drop_pending_updates=False)
    await close_mongo()


async def run_polling() -> None:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    await on_startup(bot)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(bot)
        await bot.session.close()


async def run_webhook() -> None:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host=settings.host, port=settings.port)


def main() -> None:
    setup_logging()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty")
    if uvloop and sys.platform != "win32":
        uvloop.install()
    if settings.use_webhook or settings.mode == "webhook":
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
