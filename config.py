"""Central configuration — sab env variables yahan se load hote hain."""
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
APP_LINK = os.environ.get("APP_LINK", "https://post-bot-i3rk.onrender.com").rstrip("/")
DEFAULT_CHANNEL = os.environ.get("DEFAULT_CHANNEL", "@novelxplin")
OWNER_ID = int(os.environ.get("OWNER_ID", "6069200310"))
PORT = int(os.environ.get("PORT", 8080))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

MAX_BUTTONS = 10
SESSION_TTL = 30 * 60  # 30 minutes
