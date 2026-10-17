"""Configuration loaded from environment variables."""
import os
import logging

logger = logging.getLogger(__name__)

BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "").strip()
PORT: int = int(os.environ.get("PORT", "10000"))
TZ: str = os.environ.get("TZ", "Asia/Kolkata")
DATA_DIR: str = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning("Ignoring invalid ADMIN_IDS entry: %r", part)
    return ids


ADMIN_IDS: set[int] = _parse_admin_ids(os.environ.get("ADMIN_IDS", ""))


def validate() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set. "
            "Get a token from @BotFather and set BOT_TOKEN in your Render dashboard."
        )
    if ADMIN_IDS:
        logger.info("Bot restricted to %d admin(s)", len(ADMIN_IDS))
    else:
        logger.warning("ADMIN_IDS not set - bot is open to everyone!")
