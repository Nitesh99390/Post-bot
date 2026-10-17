"""Post data model + helpers for building keyboards and sending."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.constants import ParseMode

# Button syntax (one row per line):
#   Text - https://url.com | Text 2 - https://url2.com
BUTTON_LINE_RE = re.compile(r"^\s*(.+?)\s*-\s*(https?://\S+|tg://\S+|t\.me/\S+)\s*$")


@dataclass
class Post:
    media_type: str | None = None  # photo | video | animation | document | audio | None
    file_id: str | None = None
    text: str = ""
    parse_mode: str = ParseMode.HTML
    buttons: list[list[dict[str, str]]] = field(default_factory=list)
    disable_preview: bool = False
    protect_content: bool = False
    silent: bool = False
    pin: bool = False

    # ---------------------------------------------------------------- utils
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Post":
        return cls(**d)

    def is_empty(self) -> bool:
        return not self.text and not self.file_id

    def keyboard(self) -> InlineKeyboardMarkup | None:
        if not self.buttons:
            return None
        rows = [
            [InlineKeyboardButton(b["text"], url=b["url"]) for b in row]
            for row in self.buttons
        ]
        return InlineKeyboardMarkup(rows)

    # ---------------------------------------------------------------- send
    async def send(self, bot: Bot, chat_id: int | str) -> Message:
        kb = self.keyboard()
        common = dict(
            chat_id=chat_id,
            reply_markup=kb,
            disable_notification=self.silent,
            protect_content=self.protect_content,
        )
        if self.media_type is None:
            msg = await bot.send_message(
                text=self.text or " ",
                parse_mode=self.parse_mode,
                disable_web_page_preview=self.disable_preview,
                **common,
            )
        else:
            caption = self.text or None
            sender = {
                "photo": bot.send_photo,
                "video": bot.send_video,
                "animation": bot.send_animation,
                "document": bot.send_document,
                "audio": bot.send_audio,
            }[self.media_type]
            kwargs = {self.media_type: self.file_id}
            msg = await sender(caption=caption, parse_mode=self.parse_mode, **kwargs, **common)

        if self.pin:
            try:
                await bot.pin_chat_message(chat_id, msg.message_id, disable_notification=True)
            except Exception:  # noqa: BLE001 - pinning is best-effort
                pass
        return msg


def parse_buttons(raw: str) -> list[list[dict[str, str]]]:
    """Parse button text into rows. Raises ValueError on bad syntax."""
    rows: list[list[dict[str, str]]] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        row: list[dict[str, str]] = []
        for part in line.split("|"):
            m = BUTTON_LINE_RE.match(part)
            if not m:
                raise ValueError(f"Invalid button: <code>{part.strip()}</code>")
            text, url = m.group(1), m.group(2)
            if url.startswith("t.me/"):
                url = "https://" + url
            row.append({"text": text, "url": url})
        if row:
            rows.append(row)
    if not rows:
        raise ValueError("No buttons found.")
    return rows


def extract_media(message: Message) -> tuple[str | None, str | None]:
    """Return (media_type, file_id) for a message, or (None, None)."""
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.animation:
        return "animation", message.animation.file_id
    if message.document:
        return "document", message.document.file_id
    if message.audio:
        return "audio", message.audio.file_id
    return None, None


def message_html(message: Message) -> str:
    """Get text/caption from a message preserving formatting as HTML."""
    if message.text:
        return message.text_html or message.text
    if message.caption:
        return message.caption_html or message.caption
    return ""
