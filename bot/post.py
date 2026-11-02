"""Post validation and Telegram delivery."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

COLORS = {
    "blue": ("Blue", "primary"),
    "green": ("Green", "success"),
    "red": ("Red", "danger"),
}
MAX_BUTTONS = 10
MAX_BUTTON_TEXT = 64
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4000
MEDIA_NAMES = {
    "photo": "Photo",
    "video": "Video",
    "animation": "GIF",
    "sticker": "Sticker",
}


def plain_len(html_text: str) -> int:
    text = html.unescape(re.sub(r"<[^>]+>", "", html_text))
    return len(text.encode("utf-16-le")) // 2


def normalize_url(raw: str) -> str | None:
    value = raw.strip()
    if (
        not value
        or len(value) > 2048
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        return None
    if re.fullmatch(r"@[A-Za-z0-9_]{4,32}", value):
        return "https://t.me/" + value[1:]
    if "\\" in value:
        return None
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        if (
            parts.scheme.lower() not in ("http", "https")
            or parts.username
            or parts.password
        ):
            return None
        host = (parts.hostname or "").encode("idna").decode("ascii")
        if len(host) > 253 or "." not in host:
            return None
        if any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in host.split(".")
        ):
            return None
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            return None
    except (ValueError, UnicodeError):
        return None
    netloc = host.lower() + (f":{port}" if port is not None else "")
    return urlunsplit(
        (parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment)
    )


@dataclass
class Post:
    media_type: str | None = None
    file_id: str | None = None
    text: str = ""
    buttons: list[dict[str, str]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.file_id and not self.text.strip() and not self.buttons

    def validate(self) -> None:
        if self.media_type not in (None, *MEDIA_NAMES) or bool(self.media_type) != bool(
            self.file_id
        ):
            raise ValueError("Send a supported photo, video, GIF or sticker.")
        if plain_len(self.text) > TEXT_LIMIT:
            raise ValueError(
                f"Text is too long. Use up to {TEXT_LIMIT} units; some symbols count as two."
            )
        if len(self.buttons) > MAX_BUTTONS:
            raise ValueError(f"Use up to {MAX_BUTTONS} buttons per post.")
        for button in self.buttons:
            label = button.get("text", "")
            if (
                not label.strip()
                or len(label.encode("utf-16-le")) // 2 > MAX_BUTTON_TEXT
            ):
                raise ValueError(
                    f"Button names must be 1–{MAX_BUTTON_TEXT} units long."
                )
            if (
                not normalize_url(button.get("url", ""))
                or button.get("color") not in COLORS
            ):
                raise ValueError(
                    "Use a valid HTTP or HTTPS button link and choose a colour."
                )

    def keyboard(self) -> InlineKeyboardMarkup | None:
        if not self.buttons:
            return None
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        b["text"], url=b["url"], style=COLORS[b["color"]][1]
                    )
                ]
                for b in self.buttons
            ]
        )

    async def send(self, bot: Bot, chat_id: int | str) -> Message | None:
        self.validate()
        if self.is_empty():
            return None
        body, keyboard = self.text.strip(), self.keyboard()
        if self.media_type is None:
            return await bot.send_message(
                chat_id,
                body or "View details",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
        if self.media_type == "sticker":
            if not body:
                return await bot.send_sticker(
                    chat_id, self.file_id, reply_markup=keyboard
                )
            await bot.send_sticker(chat_id, self.file_id)
        else:
            sender = {
                "photo": bot.send_photo,
                "video": bot.send_video,
                "animation": bot.send_animation,
            }[self.media_type]
            if plain_len(body) <= CAPTION_LIMIT:
                return await sender(
                    chat_id,
                    self.file_id,
                    caption=body or None,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
            await sender(chat_id, self.file_id)
        return await bot.send_message(
            chat_id, body, reply_markup=keyboard, parse_mode=ParseMode.HTML
        )


def extract_media(message: Message) -> tuple[str | None, str | None]:
    for kind in ("animation", "sticker", "photo", "video"):
        media = getattr(message, kind, None)
        if media:
            return kind, media[-1].file_id if kind == "photo" else media.file_id
    return None, None
