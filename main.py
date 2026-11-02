#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from contextlib import suppress

import aiohttp
from aiohttp import web
from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import AIORateLimiter, Application, PicklePersistence
from telegram.request import HTTPXRequest

from bot.config import ConfigError, settings
from bot.handlers import register

logger = logging.getLogger("main")
STARTED_AT = time.time()


def setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        level=getattr(logging, settings.log_level, logging.INFO),
        stream=sys.stdout,
    )
    for noisy in ("httpx", "httpcore", "aiohttp.access", "telegram.ext.Updater"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------- web
def build_web(app: Application) -> web.Application:
    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "mode": "webhook" if settings.use_webhook else "polling",
                "uptime": int(time.time() - STARTED_AT),
            }
        )

    async def webhook(request: web.Request) -> web.Response:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.webhook_secret:
            return web.Response(status=403)
        try:
            payload = await request.json()
            update = Update.de_json(payload, app.bot)
        except Exception:  # noqa: BLE001
            return web.Response(status=400)
        if update is None:
            return web.Response(status=400)
        await app.update_queue.put(update)
        return web.Response(status=200)

    web_app = web.Application(client_max_size=2 * 1024 * 1024)
    web_app.router.add_get("/", health)
    web_app.router.add_get("/health", health)
    web_app.router.add_post(settings.webhook_path, webhook)
    return web_app


async def keep_alive() -> None:
    url = f"{settings.base_url}/health"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            await asyncio.sleep(settings.keep_alive_interval)
            with suppress(Exception):
                async with session.get(url) as resp:
                    logger.debug("Keep-alive ping → %s", resp.status)


# ---------------------------------------------------------------- bot
def build_application(base_url: str | None = None) -> Application:
    os.makedirs(os.path.dirname(settings.persistence_file) or ".", exist_ok=True)
    request = HTTPXRequest(connection_pool_size=32, connect_timeout=15, read_timeout=30, write_timeout=30, pool_timeout=10)
    builder = Application.builder().token(settings.bot_token)
    if base_url:
        builder = builder.base_url(base_url)
    return (
        builder.request(request)
        .get_updates_request(HTTPXRequest(connection_pool_size=4, read_timeout=45))
        .rate_limiter(AIORateLimiter(max_retries=3))
        .persistence(PicklePersistence(settings.persistence_file, update_interval=30))
        .concurrent_updates(64)
        .build()
    )


async def notify_admin(app: Application, text: str) -> None:
    if not settings.admin_id:
        return
    with suppress(TelegramError):
        await app.bot.send_message(settings.admin_id, text)


async def run() -> None:
    settings.validate()
    app = build_application()
    register(app)

    runner = web.AppRunner(build_web(app), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=settings.port).start()
    logger.info("HTTP server on 0.0.0.0:%d", settings.port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    background: list[asyncio.Task] = []
    async with app:
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Open the bot"),
                BotCommand("new", "Create a new post"),
                BotCommand("help", "How it works"),
                BotCommand("cancel", "Cancel current post"),
            ]
        )
        me = await app.bot.get_me()
        await app.start()

        if settings.use_webhook:
            await app.bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=["message"],
                drop_pending_updates=True,
                max_connections=40,
            )
            logger.info("Webhook → %s", settings.webhook_url)
            if settings.keep_alive:
                background.append(asyncio.create_task(keep_alive(), name="keep-alive"))
        else:
            await app.bot.delete_webhook(drop_pending_updates=True)
            await app.updater.start_polling(allowed_updates=["message"], drop_pending_updates=True)
            logger.info("Polling mode")

        logger.info("Bot online as @%s", me.username)
        await notify_admin(app, f"✅ @{me.username} is online")

        try:
            await stop.wait()
        finally:
            logger.info("Shutting down…")
            for task in background:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if app.updater and app.updater.running:
                await app.updater.stop()
            await app.stop()
            await runner.cleanup()


def main() -> None:
    setup_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except ConfigError as e:
        logger.critical("%s", e)
        sys.exit(2)
    except Exception:  # noqa: BLE001
        logger.critical("Fatal error", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
