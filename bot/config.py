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

# Supabase (cloud storage for drafts, saved posts and stats).
# Defaults point at the project linked to this private repository. Override
# with environment variables; SUPABASE_KEY may be a sb_secret_ / service_role
# key on the server for tighter security. Set STORAGE=memory to disable.
SUPABASE_URL = (
    os.environ.get("SUPABASE_URL") or "https://tmziuejwimwzyowkvhak.supabase.co"
).strip().rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY") or "sb_publishable_yrb-RaDOBsI_cEpZPkPEeg_PmY5ea_y"
).strip()
STORAGE_ENABLED = os.environ.get("STORAGE", "supabase").strip().lower() != "memory"

# Mini App. It is served by this same process under /app/ and talks to /api/.
# WEBAPP_URL overrides the address Telegram opens (useful behind a proxy).
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()
MAX_UPLOAD = 30 * 1024 * 1024  # bytes accepted for one attached file
INIT_DATA_MAX_AGE = 3 * 24 * 60 * 60  # seconds a Mini App session stays valid


def webapp_url() -> str:
    """Public HTTPS address of the Mini App, or '' when it cannot be served."""
    if WEBAPP_URL:
        return WEBAPP_URL
    return BASE_URL + "/app/" if BASE_URL else ""


def validate() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN to the token provided by @BotFather.")
    try:
        if not 1 <= int(PORT) <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        raise RuntimeError("PORT must be an integer between 1 and 65535.") from None
    if WEBAPP_URL and not WEBAPP_URL.startswith("https://"):
        raise RuntimeError("WEBAPP_URL must be a public HTTPS URL.")
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
