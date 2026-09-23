"""Entry point — Flask (mini app) + Telegram bot polling + keep-alive ping."""
import logging
import threading
import time

import requests

from config import APP_LINK, PORT, BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("main")


def keep_alive():
    """Render free tier ko sleep hone se rokta hai."""
    while True:
        time.sleep(300)
        try:
            requests.get(APP_LINK, timeout=10)
        except Exception:
            pass


def run_web():
    from web import app
    app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()

    if not BOT_TOKEN:
        log.error("BOT_TOKEN missing — running web only.")
        while True:
            time.sleep(3600)

    from bot import bot, setup
    setup()
    log.info("Bot polling started")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
