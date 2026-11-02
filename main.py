#!/usr/bin/env python3
"""Post Maker Bot - entry point.

One small aiohttp web server does everything:
  GET  /           -> health check (Render)
  GET  /health     -> health check (Render)
  GET  /app        -> the colourful Mini App
  POST /webhook    -> Telegram updates (only when a public URL is known)

On Render (RENDER_EXTERNAL_URL is set automatically) the bot uses a webhook, so
a sleeping free instance wakes up as soon as someone messages the bot.
Locally (no public URL) it falls back to long polling.
"""
import asyncio
import logging
import os
import signal
import sys

from aiohttp import web
from telegram import BotCommand, Update
from telegram.ext import Application

from bot import config
from bot.handlers import register

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("main")

WEBAPP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp", "index.html")


# ---------------------------------------------------------------- web server
def build_web_app(application: Application) -> web.Application:
    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "post-maker-bot"})

    async def mini_app(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEBAPP_FILE, headers={"Cache-Control": "no-cache"})

    async def webhook(request: web.Request) -> web.Response:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != config.WEBHOOK_SECRET:
            return web.Response(status=403)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001 - bad body, ignore
            return web.Response(status=400)
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/app", mini_app)
    app.router.add_post(config.WEBHOOK_PATH, webhook)
    return app


# ---------------------------------------------------------------- bot
async def run() -> None:
    config.validate()

    application = Application.builder().token(config.BOT_TOKEN).build()
    register(application)

    runner = web.AppRunner(build_web_app(application))
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=config.PORT).start()
    logger.info("Web server listening on 0.0.0.0:%d", config.PORT)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    async with application:
        await application.bot.set_my_commands([BotCommand("start", "✨ Make a new post")])
        me = await application.bot.get_me()
        await application.start()

        use_webhook = config.BASE_URL.startswith("https://")
        if use_webhook:
            url = config.BASE_URL + config.WEBHOOK_PATH
            await application.bot.set_webhook(
                url=url,
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=["message"],
                drop_pending_updates=True,
            )
            logger.info("Webhook mode: %s", url)
            logger.info("Mini App: %s", config.MINI_APP_URL)
        else:
            await application.bot.delete_webhook(drop_pending_updates=True)
            await application.updater.start_polling(allowed_updates=["message"], drop_pending_updates=True)
            logger.info("Polling mode (set WEBHOOK_URL / RENDER_EXTERNAL_URL for webhook + Mini App)")

        logger.info("Bot started as @%s", me.username)
        try:
            await stop.wait()
        finally:
            logger.info("Shutting down…")
            if application.updater and application.updater.running:
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
