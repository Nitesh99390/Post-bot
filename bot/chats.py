"""Groups and channels: permission rules and linking them to users."""

from __future__ import annotations

import re
from typing import Any

from telegram import Bot, Chat

CHAT_TYPES = ("group", "supergroup", "channel")
REF_RE = re.compile(r"^(@[A-Za-z0-9_]{4,32}|-100\d{5,})$")


def chat_type(chat: Chat) -> str:
    return str(getattr(chat.type, "value", chat.type))


def is_admin(member: Any) -> bool:
    return member.status in ("creator", "administrator")


def user_can_publish(kind: str, member: Any) -> bool:
    """May this *user* post through the bot in a chat of this kind?"""
    if member.status == "creator":
        return True
    if member.status != "administrator":
        return False
    return kind != "channel" or bool(getattr(member, "can_post_messages", False))


def member_can_post(kind: str, member: Any) -> bool:
    """Can the bot (``member``) publish in a chat of this kind?"""
    status = member.status
    if status == "creator":
        return True
    if status == "administrator":
        return kind != "channel" or bool(getattr(member, "can_post_messages", False))
    if status == "member":
        return kind != "channel"
    if status == "restricted":
        return kind != "channel" and bool(getattr(member, "can_send_messages", False))
    return False


def parse_ref(raw: str) -> str | None:
    """Accept @name, t.me/name, https://t.me/name or a -100… id."""
    value = (raw or "").strip()
    match = re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/([A-Za-z0-9_]{4,32})(?:/\d+)?/?(?:[?#].*)?$", value)
    if match:
        value = "@" + match.group(1)
    if value and not value.startswith(("@", "-")) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", value):
        value = "@" + value
    return value if REF_RE.match(value) else None


def chat_info(chat: Chat, can_post: bool) -> dict[str, Any]:
    return {
        "type": chat_type(chat),
        "title": (chat.title or chat.username or str(chat.id))[:128],
        "username": chat.username,
        "can_post": can_post,
    }


async def register_chat(
    bot: Bot, store: Any, user_id: int, chat: Chat, bot_member: Any
) -> str:
    """Link ``chat`` to ``user_id`` if that user administers it.

    Returns ``linked``, ``exists`` or ``not_admin``. Telegram lookup errors
    propagate so the caller can report them; storage errors do too.
    """
    kind = chat_type(chat)
    member = await bot.get_chat_member(chat.id, user_id)
    if not user_can_publish(kind, member):
        return "not_admin"
    await store.upsert_chat(chat.id, chat_info(chat, member_can_post(kind, bot_member)))
    created = await store.link_chat(user_id, chat.id)
    return "linked" if created else "exists"
