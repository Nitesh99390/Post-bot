"""Environment configuration for polling and webhook deployments."""

import hashlib
import os
from urllib.parse import urlsplit

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
PORT = os.environ.get("PORT", "10000")
BASE_URL = (
    (os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "")
    .strip()
    .rstrip("/")
)
WEBHOOK_SECRET = hashlib.sha256(("wh:" + BOT_TOKEN).encode()).hexdigest()
WEBHOOK_PATH = "/webhook"


def validate() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN to the token provided by @BotFather.")
    try:
        if not 1 <= int(PORT) <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        raise RuntimeError("PORT must be an integer between 1 and 65535.") from None
    if BASE_URL:
        try:
            url = urlsplit(BASE_URL)
            valid = (
                url.scheme == "https"
                and url.hostname
                and not url.username
                and not url.password
                and not url.query
                and not url.fragment
                and url.port in (None, 443, 80, 88, 8443)
                and not any(c.isspace() or ord(c) < 32 for c in BASE_URL)
            )
        except ValueError:
            valid = False
        if not valid:
            raise RuntimeError(
                "WEBHOOK_URL must be a public HTTPS URL with a Telegram-supported port."
            )
