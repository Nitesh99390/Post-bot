"""Telegram bot with a health endpoint and optional authenticated webhook."""

import asyncio
import hmac
import logging
import signal
import sys
from collections import OrderedDict

from aiohttp import web
from telegram import BotCommand, MenuButtonCommands, Update
from telegram.error import TelegramError
from telegram.ext import Application

from bot import config
from bot.handlers import COMMANDS, register
from bot.store import create_store

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def build_web_app(application: Application) -> web.Application:
    recent: OrderedDict[int, None] = OrderedDict()

    async def health(_request: web.Request) -> web.Response:
        ready = application.running
        return web.json_response(
            {"status": "ok" if ready else "starting", "service": "post-maker-bot"},
            status=200 if ready else 503,
        )

    async def webhook(request: web.Request) -> web.Response:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(secret.encode(), config.WEBHOOK_SECRET.encode()):
            return web.Response(status=403)
        if not application.running:
            return web.Response(status=503, headers={"Retry-After": "5"})
        try:
            data = await request.json()
            if (
                not isinstance(data, dict)
                or type(data.get("update_id")) is not int
                or data["update_id"] < 0
            ):
                return web.Response(status=400)
            message = data.get("message")
            if not isinstance(message, dict):
                return web.Response(status=400)
            chat, sender = message.get("chat"), message.get("from")
            if (
                type(message.get("message_id")) is not int
                or type(message.get("date")) is not int
                or not isinstance(chat, dict)
                or type(chat.get("id")) is not int
                or not isinstance(sender, dict)
                or type(sender.get("id")) is not int
            ):
                return web.Response(status=400)
            update = Update.de_json(data, application.bot)
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
            OSError,
            RecursionError,
        ):
            return web.Response(status=400)
        if data["update_id"] in recent:
            return web.Response(text="ok")
        try:
            application.update_queue.put_nowait(update)
        except asyncio.QueueFull:
            return web.Response(status=503, headers={"Retry-After": "5"})
        recent[data["update_id"]] = None
        if len(recent) > 2048:
            recent.popitem(last=False)
        return web.Response(text="ok")

    app = web.Application(client_max_size=256 * 1024)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    if config.BASE_URL:
        app.router.add_post(config.WEBHOOK_PATH, webhook)
    return app


async def run() -> None:
    config.validate()
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .update_queue(asyncio.Queue(maxsize=256))
        .concurrent_updates(False)
        .connect_timeout(10)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(10)
        .build()
    )
    register(application)
    store = await create_store(
        config.SUPABASE_URL, config.SUPABASE_KEY, config.STORAGE_ENABLED
    )
    application.bot_data["store"] = store
    runner = web.AppRunner(build_web_app(application), access_log=None)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await runner.setup()
        await web.TCPSite(runner, host="0.0.0.0", port=int(config.PORT)).start()
        async with application:
            try:
                await application.bot.set_my_commands(
                    [BotCommand(name, about) for name, _, about in COMMANDS]
                )
                await application.bot.set_chat_menu_button(
                    menu_button=MenuButtonCommands()
                )
                await application.start()
                if config.BASE_URL:
                    await application.bot.set_webhook(
                        url=config.BASE_URL + config.WEBHOOK_PATH,
                        secret_token=config.WEBHOOK_SECRET,
                        allowed_updates=["message"],
                        max_connections=10,
                        drop_pending_updates=False,
                    )
                    logger.info("Webhook mode enabled")
                else:
                    await application.bot.delete_webhook(drop_pending_updates=False)
                    await application.updater.start_polling(
                        allowed_updates=["message"], drop_pending_updates=False
                    )
                    logger.info("Polling mode enabled")
                logger.info("Bot ready")
                await stop.wait()
            finally:
                await runner.cleanup()
                if application.updater and application.updater.running:
                    await application.updater.stop()
                if application.running:
                    await application.stop()
    finally:
        await runner.cleanup()
        await store.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    except RuntimeError as error:
        logger.error("%s", error)
        sys.exit(1)
    except (TelegramError, OSError) as error:
        logger.error(
            "Startup failed (%s). Check configuration and Telegram connectivity.",
            type(error).__name__,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
