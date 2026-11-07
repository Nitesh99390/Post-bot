"""Validation of Telegram Mini App ``initData`` (HMAC-SHA-256 scheme).

Every API request carries the raw ``Telegram.WebApp.initData`` string. It is
signed by Telegram with a key derived from the bot token, so a valid
signature proves which user opened the Mini App without any login screen.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class AuthError(Exception):
    """initData is missing, forged or too old."""


def _secret(token: str) -> bytes:
    return hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()


def sign(fields: dict[str, str], token: str) -> str:
    """Hash of ``fields`` as Telegram computes it (also used by tests/dev)."""
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    return hmac.new(_secret(token), check.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    raw: str, token: str, max_age: int = 86400, now: float | None = None
) -> dict:
    """Return the Telegram user dict from ``raw`` or raise ``AuthError``."""
    if not raw or not token or len(raw) > 8192:
        raise AuthError("missing")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=40)
    except ValueError:
        raise AuthError("malformed") from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise AuthError("duplicate fields")
    received = fields.pop("hash", "")
    # Only ``hash`` is excluded; ``signature`` stays part of the HMAC input.
    if not hmac.compare_digest(received.encode(), sign(fields, token).encode()):
        raise AuthError("bad signature")
    try:
        age = (time.time() if now is None else now) - int(fields["auth_date"])
        user = json.loads(fields["user"])
    except (KeyError, ValueError):
        raise AuthError("incomplete") from None
    if age > max_age or age < -300:
        raise AuthError("expired")
    if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
        raise AuthError("no user")
    return user
