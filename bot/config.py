from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")


class ConfigError(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    port: int
    base_url: str
    webhook_path: str
    webhook_secret: str
    admin_id: int | None
    persistence_file: str
    keep_alive: bool
    keep_alive_interval: int
    log_level: str

    @property
    def use_webhook(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def webhook_url(self) -> str:
        return f"{self.base_url}{self.webhook_path}" if self.use_webhook else ""

    def validate(self) -> None:
        if not self.bot_token:
            raise ConfigError("BOT_TOKEN is not set. Get one from @BotFather and add it to the environment.")
        if not _TOKEN_RE.match(self.bot_token):
            raise ConfigError("BOT_TOKEN looks invalid. Expected format: 123456789:AbCdEf...")
        if not 1 <= self.port <= 65535:
            raise ConfigError(f"PORT must be between 1 and 65535, got {self.port}.")
        if self.base_url and not self.use_webhook:
            raise ConfigError("WEBHOOK_URL must start with https:// (Telegram requires TLS).")

    @classmethod
    def from_env(cls) -> Settings:
        token = _env("BOT_TOKEN")
        base_url = (_env("WEBHOOK_URL") or _env("RENDER_EXTERNAL_URL")).rstrip("/")
        secret = hashlib.sha256(f"webhook:{token}".encode()).hexdigest()[:48]
        admin = _int("ADMIN_ID", 0)
        return cls(
            bot_token=token,
            port=_int("PORT", 10000),
            base_url=base_url,
            webhook_path=_env("WEBHOOK_PATH", "/webhook"),
            webhook_secret=secret,
            admin_id=admin or None,
            persistence_file=_env("PERSISTENCE_FILE", "data/state.pickle"),
            keep_alive=_bool("KEEP_ALIVE", True),
            keep_alive_interval=max(60, _int("KEEP_ALIVE_INTERVAL", 600)),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
        )


settings = Settings.from_env()
