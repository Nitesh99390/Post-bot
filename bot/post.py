from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

COLORS: dict[str, tuple[str, str]] = {
    "red": ("🔴 Red", "danger"),
    "green": ("🟢 Green", "success"),
    "blue": ("🔵 Blue", "primary"),
}

MAX_BUTTONS = 10
MAX_BUTTON_TEXT = 64
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4000

MEDIA_NAMES = {"photo": "Photo", "video": "Video", "animation": "GIF", "sticker": "Sticker"}

_TAG_RE = re.compile(r"<[^>]+>")
_USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{3,31}$")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_HOST_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


def plain_len(html_text: str) -> int:
    return len(html.unescape(_TAG_RE.sub("", html_text)))


def normalize_url(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s or any(ch.isspace() for ch in s):
        return None
    if s.startswith("@") and _USERNAME_RE.match(s):
        return f"https://t.me/{s[1:]}"
    if s.lower().startswith("tg://"):
        return s if len(s) > 5 else None
    if not _SCHEME_RE.match(s):
        s = f"https://{s}"
    parsed = urlparse(s)
    if parsed.scheme.lower() not in ("http", "https"):
        return None
    host = parsed.hostname or ""
    if not _HOST_RE.match(host):
        return None
    return s


@dataclass(slots=True)
class Button:
    text: str
    url: str
    color: str = "blue"

    def to_inline(self) -> InlineKeyboardButton:
        style = COLORS.get(self.color, COLORS["blue"])[1]
        return InlineKeyboardButton(self.text, url=self.url, style=style)

    def to_dict(self) -> dict[str, str]:
        return {"text": self.text, "url": self.url, "color": self.color}

    @classmethod
    def from_dict(cls, data: dict) -> Button:
        return cls(str(data.get("text", "")), str(data.get("url", "")), str(data.get("color", "blue")))


@dataclass(slots=True)
class Post:
    media_type: str | None = None
    file_id: str | None = None
    emoji: str = ""
    text: str = ""
    buttons: list[Button] = field(default_factory=list)

    def body(self) -> str:
        return "\n\n".join(p for p in (self.emoji.strip(), self.text.strip()) if p)

    def is_empty(self) -> bool:
        return not self.file_id and not self.body() and not self.buttons

    def has_media(self) -> bool:
        return bool(self.media_type and self.file_id)

    def keyboard(self) -> InlineKeyboardMarkup | None:
        if not self.buttons:
            return None
        return InlineKeyboardMarkup([[b.to_inline()] for b in self.buttons])

    def summary(self) -> str:
        parts: list[str] = []
        if self.has_media():
            parts.append(MEDIA_NAMES.get(self.media_type or "", "Media"))
        if self.body():
            parts.append(f"Text ({plain_len(self.body())})")
        if self.buttons:
            parts.append(f"{len(self.buttons)} button{'s' if len(self.buttons) != 1 else ''}")
        return " · ".join(parts) if parts else "Empty"

    def to_dict(self) -> dict:
        return {
            "media_type": self.media_type,
            "file_id": self.file_id,
            "emoji": self.emoji,
            "text": self.text,
            "buttons": [b.to_dict() for b in self.buttons],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Post:
        return cls(
            media_type=data.get("media_type"),
            file_id=data.get("file_id"),
            emoji=str(data.get("emoji", "")),
            text=str(data.get("text", "")),
            buttons=[Button.from_dict(b) for b in data.get("buttons", []) if isinstance(b, dict)],
        )

    async def send(self, bot: Bot, chat_id: int | str) -> Message | None:
        body = self.body()
        kb = self.keyboard()

        if not self.has_media():
            if not body and not kb:
                return None
            return await bot.send_message(chat_id, body or "\u200b", reply_markup=kb, parse_mode=ParseMode.HTML)

        if self.media_type == "sticker":
            if not body:
                return await bot.send_sticker(chat_id, self.file_id, reply_markup=kb)
            await bot.send_sticker(chat_id, self.file_id)
            return await bot.send_message(chat_id, body, reply_markup=kb, parse_mode=ParseMode.HTML)

        sender = {"photo": bot.send_photo, "video": bot.send_video, "animation": bot.send_animation}[self.media_type]
        if plain_len(body) <= CAPTION_LIMIT:
            return await sender(chat_id, self.file_id, caption=body or None, reply_markup=kb, parse_mode=ParseMode.HTML)

        await sender(chat_id, self.file_id)
        return await bot.send_message(chat_id, body, reply_markup=kb, parse_mode=ParseMode.HTML)


def extract_media(message: Message) -> tuple[str | None, str | None]:
    if message.animation:
        return "animation", message.animation.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    return None, None
