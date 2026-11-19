from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    Message,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

COLORS = {
    "blue": ("🔵 Blue", "primary"),
    "green": ("🟢 Green", "success"),
    "red": ("🔴 Red", "danger"),
}
STYLE_TO_COLOR = {style: key for key, (_, style) in COLORS.items()}
MAX_BUTTONS = 10
MAX_BUTTON_TEXT = 64
MAX_COLUMNS = 3
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
NO_CAPTION = {"sticker", "video_note"}
SPOILER_MEDIA = {"photo", "video", "animation"}
EDITABLE_MEDIA = {
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
    "animation": InputMediaAnimation,
    "audio": InputMediaAudio,
    "document": InputMediaDocument,
}
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

_MENTION_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9_]{3,31}$")
_TME_INVITE_RE = re.compile(r"^(?:https?://)?t\.me/\+[A-Za-z0-9_-]{4,64}$", re.IGNORECASE)


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
    if _MENTION_RE.fullmatch(value):
        return "https://t.me/" + value[1:]
    if _TME_INVITE_RE.fullmatch(value):
        suffix = value.split("t.me/", 1)[1]
        return "https://t.me/" + suffix
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
        labels = host.split(".")
        if any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
            for part in labels
        ):
            return None
        if labels[-1].isdigit():
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


def _parse_single_pair(segment: str) -> dict[str, str] | None:
    match = _QUICK_PIPE.match(segment) or _QUICK_DASH.match(segment)
    if not match:
        return None
    label, url = match.group(1).strip(), normalize_url(match.group(2))
    if not url or not label or utf16_len(label) > MAX_BUTTON_TEXT:
        return None
    return {"text": label, "url": url}


def parse_quick_buttons(raw: str) -> list[dict[str, Any]] | None:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return None
    items: list[dict[str, Any]] = []
    for line in lines:
        if "&&" in line:
            parts = [part.strip() for part in line.split("&&")]
            if not all(parts) or len(parts) > MAX_COLUMNS:
                return None
            row_items = [_parse_single_pair(part) for part in parts]
            if any(item is None for item in row_items):
                return None
            for idx, item in enumerate(row_items):
                assert item is not None
                if idx > 0:
                    item["same_row"] = True
                items.append(item)
        else:
            parsed = _parse_single_pair(line)
            if parsed is None:
                return None
            items.append(parsed)
    return items


@dataclass
class Post:
    media_type: str | None = None
    file_id: str | None = None
    text: str = ""
    buttons: list[dict[str, Any]] = field(default_factory=list)
    link_preview: bool = True
    columns: int = 1
    spoiler: bool = False
    caption_above: bool = False
    protect: bool = False
    silent: bool = False

    def is_empty(self) -> bool:
        return not self.file_id and not self.plain_text() and not self.buttons

    def validate(self) -> None:
        if self.media_type not in (None, *MEDIA_NAMES) or bool(self.media_type) != bool(
            self.file_id
        ):
            raise ValueError("Send a supported photo, video, GIF, sticker, audio or file.")
        if plain_len(self.text) > TEXT_LIMIT:
            raise ValueError(
                f"Text is too long. Use up to {TEXT_LIMIT} units; some symbols count as two."
            )
        if type(self.columns) is not int or not 1 <= self.columns <= MAX_COLUMNS:
            raise ValueError(f"Button columns must be between 1 and {MAX_COLUMNS}.")
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> Post | None:
        if not isinstance(data, dict):
            return None
        try:
            cols = data.get("columns", 1)
            columns = int(cols) if type(cols) is int or (isinstance(cols, str) and cols.isdigit()) else 1
            buttons: list[dict[str, Any]] = []
            for b in data.get("buttons") or []:
                entry: dict[str, Any] = {
                    "text": str(b["text"]),
                    "url": str(b["url"]),
                    "color": str(b.get("color", "blue")),
                }
                if b.get("same_row"):
                    entry["same_row"] = True
                buttons.append(entry)
            post = cls(
                media_type=data.get("media_type") or None,
                file_id=data.get("file_id") or None,
                text=str(data.get("text") or ""),
                buttons=buttons,
                link_preview=bool(data.get("link_preview", True)),
                columns=columns,
                spoiler=bool(data.get("spoiler", False)),
                caption_above=bool(data.get("caption_above", False)),
                protect=bool(data.get("protect", False)),
                silent=bool(data.get("silent", False)),
            )
            post.validate()
        except (TypeError, KeyError, ValueError, AttributeError):
            return None
        return post

    def plain_text(self) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", self.text)).strip()

    def supports_spoiler(self) -> bool:
        return self.media_type in SPOILER_MEDIA

    def supports_caption_above(self) -> bool:
        return self.media_type in SPOILER_MEDIA

    def default_name(self) -> str:
        for line in self.plain_text().splitlines():
            line = line.strip()
            if line:
                return line[:39] + "…" if len(line) > 40 else line
        if self.media_type:
            return f"{MEDIA_NAMES[self.media_type]} post"
        return "Untitled post"

    def splits_text(self) -> bool:
        body = self.text.strip()
        if not self.media_type or not self.plain_text():
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
        btn_info = f"🔗 {len(self.buttons)}/{MAX_BUTTONS}"
        if self.columns > 1 and len(self.buttons) > 1:
            btn_info += f" ({self.columns} col)"
        parts.append(btn_info)
        flags = []
        if not self.link_preview:
            flags.append("🚫 preview off")
        if self.spoiler and self.supports_spoiler():
            flags.append("🫣 spoiler")
        if self.caption_above and self.supports_caption_above():
            flags.append("⬆️ top caption")
        if self.protect:
            flags.append("🛡 protected")
        if self.silent:
            flags.append("🔕 silent")
        parts.extend(flags)
        return "  ·  ".join(parts)

    def button_rows(self) -> list[list[InlineKeyboardButton]]:
        if not self.buttons:
            return []
        rows: list[list[InlineKeyboardButton]] = []
        has_explicit_rows = any(b.get("same_row") for b in self.buttons)
        if has_explicit_rows and self.columns == 1:
            for b in self.buttons:
                btn = InlineKeyboardButton(
                    b["text"], url=b["url"], style=COLORS[b["color"]][1]
                )
                if b.get("same_row") and rows and len(rows[-1]) < MAX_COLUMNS:
                    rows[-1].append(btn)
                else:
                    rows.append([btn])
        else:
            step = max(1, min(self.columns, MAX_COLUMNS))
            for i in range(0, len(self.buttons), step):
                rows.append(
                    [
                        InlineKeyboardButton(
                            b["text"], url=b["url"], style=COLORS[b["color"]][1]
                        )
                        for b in self.buttons[i : i + step]
                    ]
                )
        return rows

    def keyboard(self) -> InlineKeyboardMarkup | None:
        rows = self.button_rows()
        return InlineKeyboardMarkup(rows) if rows else None

    def build_input_media(self, *, body: str = "", preview_mode: bool = False) -> Any | None:
        cls = EDITABLE_MEDIA.get(self.media_type or "")
        if cls is None or not self.file_id:
            return None
        kwargs: dict[str, Any] = {
            "media": self.file_id,
            "caption": body or None,
            "parse_mode": ParseMode.HTML,
        }
        if self.supports_spoiler():
            kwargs["has_spoiler"] = bool(self.spoiler)
        if self.supports_caption_above():
            kwargs["show_caption_above_media"] = bool(self.caption_above and body)
        return cls(**kwargs)

    async def send_all(
        self,
        bot: Bot,
        chat_id: int | str,
        *,
        silent: bool | None = None,
        protect: bool | None = None,
    ) -> list[Message]:
        self.validate()
        if self.is_empty():
            return []
        body = self.text.strip() if self.plain_text() else ""
        keyboard = self.keyboard()
        preview = None if self.link_preview else LinkPreviewOptions(is_disabled=True)
        use_silent = self.silent if silent is None else silent
        use_protect = self.protect if protect is None else protect
        extra: dict[str, Any] = {}
        if use_silent:
            extra["disable_notification"] = True
        if use_protect:
            extra["protect_content"] = True

        media_extra = dict(extra)
        if self.spoiler and self.supports_spoiler():
            media_extra["has_spoiler"] = True
        if self.caption_above and self.supports_caption_above() and body:
            media_extra["show_caption_above_media"] = True

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
            return [await send_text(body or "View details")]
        if self.media_type in NO_CAPTION:
            sender = {
                "sticker": bot.send_sticker,
                "video_note": bot.send_video_note,
            }[self.media_type]
            if not body:
                return [await sender(chat_id, self.file_id, reply_markup=keyboard, **extra)]
            first = await sender(chat_id, self.file_id, **extra)
            second = await send_text(body)
            return [first, second]
        sender = {
            "photo": bot.send_photo,
            "video": bot.send_video,
            "animation": bot.send_animation,
            "voice": bot.send_voice,
            "audio": bot.send_audio,
            "document": bot.send_document,
        }[self.media_type]
        if plain_len(body) <= CAPTION_LIMIT:
            msg = await sender(
                chat_id,
                self.file_id,
                caption=body or None,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                **media_extra,
            )
            return [msg]
        split_extra = dict(extra)
        if self.spoiler and self.supports_spoiler():
            split_extra["has_spoiler"] = True
        first = await sender(chat_id, self.file_id, **split_extra)
        second = await send_text(body)
        return [first, second]

    async def send(
        self, bot: Bot, chat_id: int | str, *, silent: bool | None = None
    ) -> Message | None:
        sent = await self.send_all(bot, chat_id, silent=silent)
        return sent[-1] if sent else None

    async def sync_preview(
        self,
        bot: Bot,
        chat_id: int,
        prev_ids: list[int],
        prev_meta: dict[str, Any] | None,
    ) -> tuple[list[int], dict[str, Any]]:
        """Update existing preview message(s) in place when Telegram allows, else cleanly replace."""
        self.validate()
        if self.is_empty():
            return [], {}
        body = self.text.strip() if self.plain_text() else ""
        display_text = body or "View details"
        keyboard = self.keyboard()
        preview = LinkPreviewOptions(is_disabled=not self.link_preview)
        split = self.splits_text()
        current_meta = {
            "media_type": self.media_type,
            "file_id": self.file_id,
            "body": body,
            "split": split,
            "spoiler": bool(self.spoiler and self.supports_spoiler()),
            "caption_above": bool(
                self.caption_above and self.supports_caption_above() and body
            ),
            "link_preview": bool(self.link_preview),
            "buttons": deepcopy_buttons(self.buttons),
            "columns": self.columns,
        }

        if prev_ids and prev_meta:
            if prev_meta == current_meta:
                return list(prev_ids), current_meta
            edited = await self._try_edit_in_place(
                bot, chat_id, prev_ids, prev_meta, current_meta, display_text, keyboard, preview
            )
            if edited:
                return list(prev_ids), current_meta

        # Send new preview first so if Telegram rejects it, old preview stays untouched
        sent = await self.send_all(bot, chat_id, silent=True, protect=False)
        new_ids = [m.message_id for m in sent]
        if prev_ids:
            await delete_quietly(bot, chat_id, prev_ids)
        return new_ids, current_meta

    async def _try_edit_in_place(
        self,
        bot: Bot,
        chat_id: int,
        prev_ids: list[int],
        prev_meta: dict[str, Any],
        curr_meta: dict[str, Any],
        display_text: str,
        keyboard: InlineKeyboardMarkup | None,
        preview: LinkPreviewOptions,
    ) -> bool:
        try:
            # Case 1: Text-only -> Text-only (single message)
            if (
                prev_meta.get("media_type") is None
                and self.media_type is None
                and len(prev_ids) == 1
            ):
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=prev_ids[0],
                    text=display_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    link_preview_options=preview,
                )
                return True

            # Case 2: Single media message -> Single media message (no split)
            if (
                not prev_meta.get("split")
                and not curr_meta["split"]
                and prev_meta.get("media_type") is not None
                and self.media_type is not None
                and len(prev_ids) == 1
            ):
                same_file = (
                    prev_meta.get("media_type") == self.media_type
                    and prev_meta.get("file_id") == self.file_id
                    and prev_meta.get("spoiler") == curr_meta["spoiler"]
                )
                if same_file and self.media_type in NO_CAPTION:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=prev_ids[0],
                        reply_markup=keyboard,
                    )
                    return True
                if same_file and self.media_type not in NO_CAPTION:
                    if (
                        prev_meta.get("body") == curr_meta["body"]
                        and prev_meta.get("caption_above") == curr_meta["caption_above"]
                    ):
                        await bot.edit_message_reply_markup(
                            chat_id=chat_id,
                            message_id=prev_ids[0],
                            reply_markup=keyboard,
                        )
                        return True
                    caption_kwargs: dict[str, Any] = {
                        "chat_id": chat_id,
                        "message_id": prev_ids[0],
                        "caption": curr_meta["body"] or None,
                        "parse_mode": ParseMode.HTML,
                        "reply_markup": keyboard,
                    }
                    if self.supports_caption_above():
                        caption_kwargs["show_caption_above_media"] = curr_meta[
                            "caption_above"
                        ]
                    await bot.edit_message_caption(**caption_kwargs)
                    return True
                # Media changed or spoiler toggled between editable media types
                if (
                    prev_meta.get("media_type") in EDITABLE_MEDIA
                    and self.media_type in EDITABLE_MEDIA
                ):
                    input_media = self.build_input_media(body=curr_meta["body"])
                    if input_media is not None:
                        await bot.edit_message_media(
                            chat_id=chat_id,
                            message_id=prev_ids[0],
                            media=input_media,
                            reply_markup=keyboard,
                        )
                        return True

            # Case 3: Split media + text -> Same media + updated text/buttons
            if (
                prev_meta.get("split")
                and curr_meta["split"]
                and len(prev_ids) == 2
                and prev_meta.get("media_type") == self.media_type
                and prev_meta.get("file_id") == self.file_id
                and prev_meta.get("spoiler") == curr_meta["spoiler"]
            ):
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=prev_ids[1],
                    text=curr_meta["body"],
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    link_preview_options=preview,
                )
                return True
        except BadRequest as error:
            if "message is not modified" in str(error).lower():
                return True
            return False
        except TelegramError:
            return False
        return False


def deepcopy_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(b) for b in buttons]


async def delete_quietly(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    ids = [mid for mid in dict.fromkeys(message_ids) if isinstance(mid, int) and mid > 0]
    if not ids:
        return
    if len(ids) == 1:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=ids[0])
        except TelegramError:
            pass
        return
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=ids)
    except TelegramError:
        for mid in ids:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except TelegramError:
                pass


def extract_media(message: Message) -> tuple[str | None, str | None]:
    for kind in MEDIA_ORDER:
        media = getattr(message, kind, None)
        if media:
            return kind, media[-1].file_id if kind == "photo" else media.file_id
    return None, None


def extract_buttons(message: Message) -> list[dict[str, Any]]:
    markup = getattr(message, "reply_markup", None)
    buttons: list[dict[str, Any]] = []
    for row in getattr(markup, "inline_keyboard", None) or ():
        row_added = 0
        for button in row:
            url = normalize_url(button.url or "") if button.url else None
            label = (button.text or "").strip()
            if not url or not label or utf16_len(label) > MAX_BUTTON_TEXT:
                continue
            color = STYLE_TO_COLOR.get(getattr(button, "style", None) or "", "blue")
            entry: dict[str, Any] = {"text": label, "url": url, "color": color}
            if row_added > 0 and row_added < MAX_COLUMNS:
                entry["same_row"] = True
            buttons.append(entry)
            row_added += 1
            if len(buttons) == MAX_BUTTONS:
                return buttons
    return buttons
