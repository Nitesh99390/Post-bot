"""Configuration loaded from environment variables (only what is really needed)."""
import hashlib
import os

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "").strip()
PORT: int = int(os.environ.get("PORT", "10000"))

# Public https URL of the service. Render sets RENDER_EXTERNAL_URL automatically.
# When it is set the bot uses a webhook (wakes up a sleeping free Render service)
# and the Mini App button is enabled. Locally (no URL) the bot uses polling.
BASE_URL: str = (os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")

# Secret used to verify that webhook calls really come from Telegram.
WEBHOOK_SECRET: str = hashlib.sha256(("wh:" + BOT_TOKEN).encode()).hexdigest()[:32]
WEBHOOK_PATH: str = "/webhook"

MINI_APP_URL: str = f"{BASE_URL}/app" if BASE_URL.startswith("https://") else ""


def validate() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set. "
            "Get a token from @BotFather and add BOT_TOKEN in your Render dashboard."
        )
