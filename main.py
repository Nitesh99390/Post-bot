#!/usr/bin/env python3
"""Telegram Post Bot - entry point.

Runs the Telegram bot (long polling) together with a tiny aiohttp web server
that answers Render's health checks on $PORT.
"""
import asyncio
import logging
import os
import sys

from aiohttp import web
from telegram import BotCommand
from telegram.ext import Application, Defaults
from telegram.constants import ParseMode

from bot import config
from bot.handlers import register, restore_scheduled_jobs

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("main")


# ---------------------------------------------------------------- health server
async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "telegram-post-bot"})


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.PORT)
    await site.start()
    logger.info("Health server listening on 0.0.0.0:%d", config.PORT)
    return runner


# ---------------------------------------------------------------- bot
async def post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("newpost", "Create a new post"),
            BotCommand("channels", "Manage channels"),
            BotCommand("addchannel", "Add a channel"),
            BotCommand("scheduled", "View scheduled posts"),
            BotCommand("myid", "Show your user ID"),
            BotCommand("help", "How to use"),
            BotCommand("cancel", "Cancel current action"),
        ]
    )
    n = restore_scheduled_jobs(app)
    if n:
        logger.info("Restored %d scheduled job(s)", n)
    me = await app.bot.get_me()
    logger.info("Bot started as @%s (id=%s)", me.username, me.id)


async def run() -> None:
    config.validate()
    os.makedirs(config.DATA_DIR, exist_ok=True)

    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .post_init(post_init)
        .build()
    )
    register(application)

    runner = await start_web_server()

    async with application:
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("Polling started. Press Ctrl+C to stop.")
        try:
            # Sleep forever until cancelled (SIGTERM from Render / Ctrl+C)
            await asyncio.Event().wait()
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            logger.info("Shutting down…")
            await application.updater.stop()
            await application.stop()
            await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
