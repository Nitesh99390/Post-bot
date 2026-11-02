"""Post model: media + text + coloured URL buttons, and the logic to send it."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode

# key -> (label shown to the user, Telegram Bot API button style)
COLORS: dict[str, tuple[str, str]] = {
    "red": ("🔴 Red", "danger"),
    "green": ("🟢 Green", "success"),
    "blue": ("🔵 Blue", "primary"),
}

MAX_BUTTONS = 10
MAX_BUTTON_TEXT = 64
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4000

CAPTION_MEDIA = ("photo", "video", "animation")
MEDIA_NAMES = {"photo": "Photo", "video": "Video", "animation": "GIF", "sticker": "Sticker"}


def plain_len(html_text: str) -> int:
    """Visible length of an HTML string (tags removed, entities decoded)."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", html_text)))


def normalize_url(raw: str) -> str | None:
    """Turn what a user typed into a valid link, or None if it is not a link.

    Accepts: https://site.com, site.com, www.site.com, t.me/name, @username
    """
    s = (raw or "").strip()
    if not s or " " in s:
        return None
    if re.fullmatch(r"@[A-Za-z0-9_]{4,32}", s):
        return "https://t.me/" + s[1:]
    if s.lower().startswith("tg://"):
        return s
    if not re.match(r"^https?://", s, re.I):
        s = "https://" + s
    p = urlparse(s)
    host = p.hostname or ""
    if p.scheme.lower() not in ("http", "https") or "." not in host or host.startswith(".") or host.endswith("."):
        return None
    return s


@dataclass
class Post:
    media_type: str | None = None  # photo | video | animation | sticker | None
    file_id: str | None = None
    emoji: str = ""  # HTML - emoji / short text sent in the first step
    text: str = ""  # HTML - main text
    buttons: list[dict[str, str]] = field(default_factory=list)  # {"text", "url", "color"}

    # ------------------------------------------------------------ helpers
    def body(self) -> str:
        return "\n\n".join(p for p in (self.emoji.strip(), self.text.strip()) if p)

    def is_empty(self) -> bool:
        return not self.file_id and not self.body() and not self.buttons

    def keyboard(self) -> InlineKeyboardMarkup | None:
        if not self.buttons:
            return None
        rows = [
            [InlineKeyboardButton(b["text"], url=b["url"], style=COLORS.get(b.get("color"), (None, None))[1])]
            for b in self.buttons
        ]
        return InlineKeyboardMarkup(rows)

    # ------------------------------------------------------------ send
    async def send(self, bot: Bot, chat_id: int | str) -> Message | None:
        body = self.body()
        kb = self.keyboard()
        html_mode = dict(parse_mode=ParseMode.HTML)

        if self.media_type is None:
            if not body and not kb:
                return None
            # Telegram needs some text to show buttons
            return await bot.send_message(chat_id, body or "👇", reply_markup=kb, **html_mode)

        if self.media_type == "sticker":
            # Stickers can't have a caption -> sticker first, then text with buttons
            if not body:
                return await bot.send_sticker(chat_id, self.file_id, reply_markup=kb)
            await bot.send_sticker(chat_id, self.file_id)
            return await bot.send_message(chat_id, body, reply_markup=kb, **html_mode)

        sender = {
            "photo": bot.send_photo,
            "video": bot.send_video,
            "animation": bot.send_animation,
        }[self.media_type]

        if plain_len(body) <= CAPTION_LIMIT:
            return await sender(chat_id, self.file_id, caption=body or None, reply_markup=kb, **html_mode)
        # Text too long for a caption -> media first, then the text with buttons
        await sender(chat_id, self.file_id)
        return await bot.send_message(chat_id, body, reply_markup=kb, **html_mode)


def extract_media(message: Message) -> tuple[str | None, str | None]:
    """Return (media_type, file_id) for supported media, else (None, None)."""
    if message.animation:  # check GIF before document/video
        return "animation", message.animation.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    return None, None
