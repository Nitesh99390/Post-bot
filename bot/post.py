"""Post model, validation, serialisation and Telegram delivery."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

COLORS = {
    "blue": ("🔵 Blue", "primary"),
    "green": ("🟢 Green", "success"),
    "red": ("🔴 Red", "danger"),
    "plain": ("⚪ Plain", None),
}
STYLE_TO_COLOR = {style: key for key, (_, style) in COLORS.items() if style}
MAX_BUTTONS = 10
MAX_BUTTON_TEXT = 64
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4000
MEDIA_NAMES = {
    "photo": "Photo",
    "video": "Video",
    "animation": "GIF",
    "sticker": "Sticker",
    "video_note": "Video message",
    "voice": "Voice",
    "audio": "Audio",
    "document": "File",
}
MEDIA_ICONS = {
    "photo": "🖼",
    "video": "🎬",
    "animation": "🎞",
    "sticker": "🌟",
    "video_note": "⏺",
    "voice": "🎙",
    "audio": "🎵",
    "document": "📄",
}
# Media that cannot carry a caption: text is delivered as a second message.
NO_CAPTION = {"sticker", "video_note"}
# Checked in this order; GIF messages also carry a document, so it goes first.
MEDIA_ORDER = (
    "animation",
    "sticker",
    "photo",
    "video",
    "video_note",
    "voice",
    "audio",
    "document",
)


class PartialSend(Exception):
    """Media went out but the follow-up text message failed."""

    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error = error


_TAGS = {
    "b": "b", "strong": "b",
    "i": "i", "em": "i",
    "u": "u", "ins": "u",
    "s": "s", "strike": "s", "del": "s",
    "code": "code", "pre": "pre",
    "tg-spoiler": "tg-spoiler",
    "blockquote": "blockquote",
    "a": "a",
}
_BLOCKS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
_EMPTY = re.compile(r"<(b|i|u|s|code|pre|tg-spoiler|blockquote)></\1>|<a href=\"[^\"]*\"></a>")


class _Cleaner(HTMLParser):
    """Rebuild arbitrary HTML as the strict subset Telegram accepts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[tuple[str | None, str]] = []

    def _open_names(self) -> list[str]:
        return [name for name, _ in self.stack if name]

    def _newline(self) -> None:
        text = "".join(self.out)
        if text and not text.endswith("\n"):
            self.out.append("\n")

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "br":
            self.out.append("\n")
            return
        if tag in _BLOCKS:
            self._newline()
        name = _TAGS.get(tag)
        opened = self._open_names()
        if name == "a":
            href = normalize_url(dict(attrs).get("href") or "")
            if not href:
                name = None
        if name in opened or (
            ("pre" in opened or "code" in opened)
            and not (name == "code" and "pre" in opened and "code" not in opened)
        ):
            name = None  # nested duplicates / formatting inside code are dropped
        if name:
            if name == "a":
                self.out.append(f'<a href="{html.escape(href, quote=True)}">')
            else:
                self.out.append(f"<{name}>")
        self.stack.append((name, tag))

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS:
            self._newline()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][1] == tag:
                while len(self.stack) > index:
                    name, _ = self.stack.pop()
                    if name:
                        self.out.append(f"</{name}>")
                return

    def handle_data(self, data: str) -> None:
        self.out.append(html.escape(data.replace("\xa0", " "), quote=False))

    def result(self) -> str:
        self.close()
        while self.stack:
            name, _ = self.stack.pop()
            if name:
                self.out.append(f"</{name}>")
        text = "".join(self.out)
        previous = None
        while previous != text:
            previous, text = text, _EMPTY.sub("", text)
        return text.strip()


def sanitize_html(text: Any) -> str:
    """Return ``text`` as balanced Telegram-HTML (b i u s code pre a spoiler quote)."""
    cleaner = _Cleaner()
    cleaner.feed(str(text or "")[:20000])
    return cleaner.result()


def plain_len(html_text: str) -> int:
    text = html.unescape(re.sub(r"<[^>]+>", "", html_text))
    return len(text.encode("utf-16-le")) // 2


def utf16_len(text: str) -> int:
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


_QUICK_PIPE = re.compile(r"^(.*?\S)\s*\|\s*(\S+)$")
_QUICK_DASH = re.compile(r"^(.*\S)\s+[-–—]\s+(\S+)$")


def parse_quick_buttons(raw: str) -> list[dict[str, str]] | None:
    """Parse ``Label - link`` / ``Label | link`` lines.

    Returns the parsed buttons only when every non-empty line is valid, so
    ordinary text is never mistaken for buttons.
    """
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return None
    items = []
    for line in lines:
        match = _QUICK_PIPE.match(line) or _QUICK_DASH.match(line)
        if not match:
            return None
        label, url = match.group(1).strip(), normalize_url(match.group(2))
        if not url or not label or utf16_len(label) > MAX_BUTTON_TEXT:
            return None
        items.append({"text": label, "url": url})
    return items


@dataclass
class Post:
    media_type: str | None = None
    file_id: str | None = None
    text: str = ""
    buttons: list[dict[str, str]] = field(default_factory=list)
    link_preview: bool = True
    media_name: str = ""

    def is_empty(self) -> bool:
        return not self.file_id and not self.text.strip() and not self.buttons

    def validate(self) -> None:
        if self.media_type not in (None, *MEDIA_NAMES) or bool(self.media_type) != bool(
            self.file_id
        ):
            raise ValueError("Send a supported photo, video, GIF, sticker, audio or file.")
        if plain_len(self.text) > TEXT_LIMIT:
            raise ValueError(
                f"Text is too long. Use up to {TEXT_LIMIT} units; some symbols count as two."
            )
        if len(self.buttons) > MAX_BUTTONS:
            raise ValueError(f"Use up to {MAX_BUTTONS} buttons per post.")
        for button in self.buttons:
            label = button.get("text", "")
            if not label.strip() or utf16_len(label) > MAX_BUTTON_TEXT:
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

    # ----- serialisation -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> Post | None:
        """Rebuild a post from stored JSON; returns None for invalid data."""
        if not isinstance(data, dict):
            return None
        try:
            post = cls(
                media_type=data.get("media_type") or None,
                file_id=data.get("file_id") or None,
                text=str(data.get("text") or ""),
                buttons=[
                    {
                        "text": str(b["text"]),
                        "url": str(b["url"]),
                        "color": str(b.get("color", "blue")),
                    }
                    for b in (data.get("buttons") or [])
                ],
                link_preview=bool(data.get("link_preview", True)),
                media_name=str(data.get("media_name") or "")[:100],
            )
            post.validate()
        except (TypeError, KeyError, ValueError, AttributeError):
            return None
        return post

    # ----- presentation --------------------------------------------------
    def plain_text(self) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", self.text)).strip()

    def default_name(self) -> str:
        for line in self.plain_text().splitlines():
            line = line.strip()
            if line:
                return line[:40] + ("…" if len(line) > 40 else "")
        if self.media_type:
            return f"{MEDIA_NAMES[self.media_type]} post"
        return "Untitled post"

    def splits_text(self) -> bool:
        body = self.text.strip()
        if not self.media_type or not body:
            return False
        return self.media_type in NO_CAPTION or plain_len(body) > CAPTION_LIMIT

    def summary(self) -> str:
        parts = []
        if self.media_type:
            parts.append(
                f"{MEDIA_ICONS[self.media_type]} {MEDIA_NAMES[self.media_type]}"
            )
        length = plain_len(self.text.strip())
        if length:
            parts.append(f"📝 {length} chars")
        parts.append(f"🔗 {len(self.buttons)}/{MAX_BUTTONS}")
        if not self.link_preview:
            parts.append("🚫 preview off")
        return "  ·  ".join(parts)

    def keyboard(self) -> InlineKeyboardMarkup | None:
        if not self.buttons:
            return None
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        b["text"], url=b["url"], style=COLORS[b["color"]][1] or None
                    )
                ]
                for b in self.buttons
            ]
        )

    # ----- delivery ------------------------------------------------------
    async def send(
        self,
        bot: Bot,
        chat_id: int | str,
        *,
        silent: bool | None = None,
        media: Any = None,
        captured: list[Message] | None = None,
    ) -> Message | None:
        """Deliver the post.

        ``media`` overrides ``file_id`` (e.g. an ``InputFile`` for a fresh
        upload). Every message that carries the media is appended to
        ``captured`` so the caller can reuse Telegram's ``file_id`` afterwards.
        """
        self.validate()
        if self.is_empty():
            return None
        body, keyboard = self.text.strip(), self.keyboard()
        preview = None if self.link_preview else LinkPreviewOptions(is_disabled=True)
        extra = {"disable_notification": True} if silent else {}
        source = media if media is not None else self.file_id

        def keep(message: Message) -> Message:
            if captured is not None:
                captured.append(message)
            return message

        async def send_text(text: str) -> Message:
            return await bot.send_message(
                chat_id,
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                link_preview_options=preview,
                **extra,
            )

        if self.media_type is None:
            return await send_text(body or "View details")
        if self.media_type in NO_CAPTION:
            sender = {
                "sticker": bot.send_sticker,
                "video_note": bot.send_video_note,
            }[self.media_type]
            if not body:
                return keep(await sender(chat_id, source, reply_markup=keyboard, **extra))
            keep(await sender(chat_id, source, **extra))
            try:
                return await send_text(body)
            except TelegramError as error:
                raise PartialSend(error) from error
        sender = {
            "photo": bot.send_photo,
            "video": bot.send_video,
            "animation": bot.send_animation,
            "voice": bot.send_voice,
            "audio": bot.send_audio,
            "document": bot.send_document,
        }[self.media_type]
        if plain_len(body) <= CAPTION_LIMIT:
            return keep(
                await sender(
                    chat_id,
                    source,
                    caption=body or None,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    **extra,
                )
            )
        keep(await sender(chat_id, source, **extra))
        try:
            return await send_text(body)
        except TelegramError as error:
            raise PartialSend(error) from error


def extract_media(message: Message) -> tuple[str | None, str | None]:
    for kind in MEDIA_ORDER:
        media = getattr(message, kind, None)
        if media:
            return kind, media[-1].file_id if kind == "photo" else media.file_id
    return None, None


def extract_buttons(message: Message) -> list[dict[str, str]]:
    """Import valid URL buttons from a forwarded message, keeping their colour."""
    markup = getattr(message, "reply_markup", None)
    buttons: list[dict[str, str]] = []
    for row in getattr(markup, "inline_keyboard", None) or ():
        for button in row:
            url = normalize_url(button.url or "") if button.url else None
            label = (button.text or "").strip()
            if not url or not label or utf16_len(label) > MAX_BUTTON_TEXT:
                continue
            color = STYLE_TO_COLOR.get(getattr(button, "style", None) or "", "blue")
            buttons.append({"text": label, "url": url, "color": color})
            if len(buttons) == MAX_BUTTONS:
                return buttons
    return buttons
