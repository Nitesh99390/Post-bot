"""Private-chat post editor.

The on-screen keyboards stay deliberately small (Create Post, then Edit Text /
Add Button / Preview / Finish / Remove Last Button). Extra features are
reached through commands and smart input detection instead of extra buttons.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from copy import deepcopy
from typing import Any

from telegram import (
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.error import (
    BadRequest,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .post import (
    COLORS,
    MAX_BUTTON_TEXT,
    MAX_BUTTONS,
    Post,
    extract_buttons,
    extract_media,
    normalize_url,
    parse_quick_buttons,
    utf16_len,
)
from .store import MAX_SAVED_POSTS, MemoryStore, StoreError, clean_name

logger = logging.getLogger(__name__)

BTN_CREATE = "✨ Create Post"
BTN_TEXT, BTN_BUTTON = "✏️ Edit Text", "🔗 Add Button"
BTN_PREVIEW, BTN_DONE = "👁 Preview", "✅ Finish"
BTN_REMOVE = "↩️ Remove Last Button"
K_POST, K_STATE, K_DRAFT = "post", "state", "draft_button"
S_MEDIA, S_MENU, S_TEXT = "media", "menu", "text"
S_BTN_NAME, S_BTN_LINK, S_BTN_COLOR = "btn_name", "btn_link", "btn_color"
NO_KEYBOARD = ReplyKeyboardRemove()
LINE = "━━━━━━━━━━━━━━"
CHANNEL_RE = re.compile(r"^(@[A-Za-z0-9_]{4,32}|-100\d{5,})$")
OPEN_DEL_RE = re.compile(r"^/(open|del)_(\d{1,12})(?:@\w+)?$")


def norm(text: str) -> str:
    """Compare labels without emoji, so old and new keyboards both work."""
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


MENU_ACTIONS = {
    norm(BTN_TEXT): "text",
    norm(BTN_BUTTON): "button",
    norm(BTN_PREVIEW): "preview",
    norm(BTN_DONE): "finish",
    "done": "finish",
    norm(BTN_REMOVE): "remove",
}
COLOR_BY_LABEL = {norm(label): key for key, (label, _) in COLORS.items()}


# ----- keyboards ----------------------------------------------------------
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CREATE, style="primary")]],
        resize_keyboard=True,
        input_field_placeholder="Create your next post ✨",
    )


def choice_keyboard(post: Post) -> ReplyKeyboardMarkup:
    row = [KeyboardButton(BTN_TEXT)]
    if len(post.buttons) < MAX_BUTTONS:
        row.append(KeyboardButton(BTN_BUTTON))
    rows = [
        row,
        [KeyboardButton(BTN_PREVIEW), KeyboardButton(BTN_DONE, style="success")],
    ]
    if post.buttons:
        rows.append([KeyboardButton(BTN_REMOVE, style="danger")])
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, input_field_placeholder="Refine your post…"
    )


def color_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(label, style=style) for label, style in COLORS.values()]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Pick a colour",
    )


# ----- state helpers -------------------------------------------------------
def get_post(context: ContextTypes.DEFAULT_TYPE) -> Post:
    return context.user_data.setdefault(K_POST, Post())


def reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()


def get_store(context: ContextTypes.DEFAULT_TYPE):
    store = context.bot_data.get("store")
    if store is None:
        store = context.bot_data["store"] = MemoryStore()
    return store


async def safe_store(context, method: str, *args, default=None, **kwargs):
    """Call the store without letting storage problems break the chat."""
    try:
        return await getattr(get_store(context), method)(*args, **kwargs)
    except StoreError as error:
        logger.warning("Storage %s failed (%s)", method, error)
        return default


def esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def tip(text: str) -> str:
    return f"\n\n<i>💡 {text}</i>"


async def reply(update: Update, text: str, markup=None) -> None:
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=markup
    )


async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    await reply(update, text, choice_keyboard(get_post(context)))


def delivery_error(error: TelegramError) -> str:
    if isinstance(error, RetryAfter):
        delay = error.retry_after
        seconds = (
            int(delay.total_seconds())
            if hasattr(delay, "total_seconds")
            else int(delay)
        )
        return f"⏳ Telegram is busy. Wait {max(1, seconds)} seconds before retrying. Your draft is saved."
    if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
        return "📡 Delivery could not be confirmed. Your draft is saved. Check the chat before retrying to avoid duplicates."
    return "⚠️ Telegram could not send this post. Your draft is saved. Edit the content or remove the last button and try again."


# ----- session persistence (Supabase) -------------------------------------
def serialize(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    data: dict[str, Any] = {}
    post = context.user_data.get(K_POST)
    if isinstance(post, Post) and not post.is_empty():
        data["post"] = post.to_dict()
    for key in (K_STATE, K_DRAFT):
        if context.user_data.get(key) is not None:
            data[key] = context.user_data[key]
    return data


def restore(context: ContextTypes.DEFAULT_TYPE, data: Any) -> None:
    if not isinstance(data, dict):
        return
    post = Post.from_dict(data.get("post"))
    if post:
        context.user_data[K_POST] = post
    state = data.get(K_STATE)
    if state in (S_MEDIA, S_MENU, S_TEXT, S_BTN_NAME, S_BTN_LINK, S_BTN_COLOR):
        context.user_data[K_STATE] = state
    if isinstance(data.get(K_DRAFT), dict):
        context.user_data[K_DRAFT] = data[K_DRAFT]


async def before_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """First message from a user in this process: restore + housekeeping."""
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat:
        return
    seen: set[int] = context.bot_data.setdefault("seen_users", set())
    if user.id in seen:
        return
    seen.add(user.id)
    if not context.user_data:
        restore(context, await safe_store(context, "load_session", user.id))
    context.bot_data.setdefault("session_hash", {})[user.id] = _hash(serialize(context))
    await safe_store(
        context,
        "touch_user",
        user.id,
        {
            "first_name": (user.first_name or "")[:64],
            "username": user.username,
            "language_code": user.language_code,
        },
    )
    # Older versions set a per-chat "My profile" Mini App menu button. It
    # overrides the bot-wide default, so reset it to the native command menu.
    try:
        await context.bot.set_chat_menu_button(
            chat_id=chat.id, menu_button=MenuButtonCommands()
        )
    except TelegramError as error:
        logger.info("Menu reset skipped (%s)", type(error).__name__)


def _hash(data: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()


async def after_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    data = serialize(context)
    hashes = context.bot_data.setdefault("session_hash", {})
    digest = _hash(data)
    if hashes.get(user.id) == digest:
        return
    if data:
        await safe_store(context, "save_session", user.id, data)
    else:
        await safe_store(context, "delete_session", user.id)
    hashes[user.id] = digest


# ----- core flow -----------------------------------------------------------
def draft_header(post: Post, title: str) -> str:
    return f"<b>{title}</b>\n<code>{esc(post.summary())}</code>\n{LINE}\n"


async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    context.user_data[K_STATE] = S_MENU
    try:
        await post.send(context.bot, update.effective_chat.id)
    except TelegramError as error:
        logger.warning("Preview failed (%s)", type(error).__name__)
        return await panel(update, context, delivery_error(error))
    hint = (
        "Text is sent as a separate message with this media — forward both."
        if post.splits_text()
        else "Send new media to replace it · /save keeps it as a template."
    )
    await panel(
        update,
        context,
        draft_header(post, "👁 Preview")
        + "Refine the text, add a link button or finish your post."
        + tip(hint)
        + "\n<i>/cancel discards this draft.</i>",
    )


async def save_candidate(
    update: Update, context: ContextTypes.DEFAULT_TYPE, candidate: Post
) -> None:
    try:
        candidate.validate()
    except ValueError as error:
        await update.effective_message.reply_text(f"⚠️ {error}")
        return
    context.user_data[K_POST] = candidate
    context.user_data.pop(K_DRAFT, None)
    await show_preview(update, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    post = context.user_data.get(K_POST)
    has_draft = isinstance(post, Post) and not post.is_empty()
    reset(context)
    if has_draft:
        context.user_data[K_POST] = post
    profile = await safe_store(context, "get_profile", user.id, default={}) or {}
    saved = await safe_store(context, "list_posts", user.id, default=[]) or []
    created = int(profile.get("posts_created") or 0)
    text = (
        "<b>✨ Post Maker</b>\n<i>Compose · Refine · Share</i>\n"
        f"{LINE}\n"
        f"Hi {esc(user.first_name or 'there')}! Create polished posts with text, media "
        "and colourful link buttons — right here in chat.\n\n"
        f"📝 Posts created: <b>{created}</b>\n💾 Saved templates: <b>{len(saved)}</b>"
    )
    if has_draft:
        text += tip("You have an unfinished draft — /back to continue it.")
    else:
        text += tip("Tap ✨ Create Post to begin · /help shows every feature.")
    await reply(update, text, main_keyboard())


async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context)
    context.user_data[K_STATE] = S_MEDIA
    await reply(
        update,
        "<b>📝 New post</b>\n"
        f"{LINE}\n"
        "Send text, a photo, video, GIF, sticker, audio, voice or file.\n\n"
        "↪️ You can also <b>forward</b> an existing post — its link buttons come along."
        + tip("Bold, italic, spoilers and links are kept.")
        + "\n<i>/cancel to exit.</i>",
        NO_KEYBOARD,
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context)
    await reply(
        update,
        "🗑 Draft discarded. Start fresh whenever you're ready.",
        main_keyboard(),
    )


async def cmd_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(K_DRAFT, None)
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    context.user_data[K_STATE] = S_MENU
    await panel(update, context, draft_header(post, "📂 Your draft") + "Choose what to refine next.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(
        update,
        "<b>📖 Quick guide</b>\n"
        f"{LINE}\n"
        "<b>Create</b>\n"
        "/new — Start a new post\n"
        "/preview — View the current draft\n"
        "/back — Leave the current step\n"
        "/cancel — Discard the draft\n\n"
        "<b>Templates</b> ☁️\n"
        "/save <i>name</i> — Save the draft\n"
        "/posts — Your saved posts\n\n"
        "<b>Publish</b>\n"
        "/channel @name — Set your channel\n"
        "/publish — Post straight to it\n"
        "/linkpreview — Toggle link previews\n"
        "/stats — Your numbers\n\n"
        "<b>Smart tricks</b>\n"
        "• Forward any post to copy it with its buttons\n"
        "• In Add Button, send several at once:\n"
        "<code>Join Channel - @mychannel\nWebsite | example.com</code>\n"
        "• Send new media from the editor to replace it\n"
        "• Edit Text replaces the full text",
    )


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[K_STATE] = S_TEXT
    await reply(
        update,
        "<b>✏️ Edit text</b>\nSend the complete replacement text. Telegram formatting is preserved."
        "\n\n<i>/back keeps the current text.</i>",
        NO_KEYBOARD,
    )


async def ask_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if len(post.buttons) >= MAX_BUTTONS:
        return await panel(
            update, context, f"🔒 Your post already has {MAX_BUTTONS} buttons."
        )
    context.user_data[K_STATE] = S_BTN_NAME
    context.user_data[K_DRAFT] = {}
    await reply(
        update,
        f"<b>🔗 Button {len(post.buttons) + 1}/{MAX_BUTTONS} — label</b>\n"
        "Choose a short name, such as <i>Join Channel</i>."
        + tip(
            "Fast mode: send <code>Label - link</code>, one per line, to add several buttons at once."
        )
        + "\n<i>/back to return.</i>",
        NO_KEYBOARD,
    )


async def record_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    return await safe_store(context, "increment_posts", update.effective_user.id)


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    try:
        await post.send(context.bot, update.effective_chat.id)
    except TelegramError as error:
        logger.warning("Final delivery failed (%s)", type(error).__name__)
        return await panel(update, context, delivery_error(error))
    split = post.splits_text()
    reset(context)
    count = await record_delivery(update, context)
    profile = await safe_store(
        context, "get_profile", update.effective_user.id, default={}
    ) or {}
    channel = profile.get("default_channel")
    text = (
        "<b>🎉 Ready to share</b>\nForward the post above to your channel or group."
        + (" Forward both messages — the text was sent separately." if split else "")
    )
    if count:
        text += f"\n\n🏆 That's post <b>#{count}</b>!"
    if channel:
        text += tip(f"/publish sends your next post straight to {esc(channel)}.")
    else:
        text += tip("Set /channel @name once and /publish posts for you.")
    await reply(update, text, main_keyboard())


async def on_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, candidate = update.effective_message, deepcopy(get_post(context))
    media_type, file_id = extract_media(msg)
    state = context.user_data.get(K_STATE)
    if media_type:
        candidate.media_type, candidate.file_id = media_type, file_id
        if msg.caption is not None:
            candidate.text = msg.caption_html
    elif msg.text and state in (S_MEDIA, S_TEXT):
        candidate.text = msg.text_html
    else:
        await msg.reply_text(
            "Send text, a photo, video, GIF, sticker, audio or file. Use /back to return."
        )
        return
    if state == S_MEDIA:
        imported = extract_buttons(msg)
        if imported:
            candidate.buttons = imported
    await save_candidate(update, context, candidate)


async def on_button_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.effective_message.text or ""
    quick = parse_quick_buttons(raw)
    if quick:
        free = MAX_BUTTONS - len(get_post(context).buttons)
        if len(quick) > free:
            await update.effective_message.reply_text(
                f"⚠️ Only {free} more button(s) fit. Send fewer lines."
            )
            return
        context.user_data[K_DRAFT] = {"items": quick}
        context.user_data[K_STATE] = S_BTN_COLOR
        names = ", ".join(esc(b["text"]) for b in quick)
        await reply(
            update,
            f"🎨 Choose a colour for <b>{names}</b>.",
            color_keyboard(),
        )
        return
    name = raw.strip()
    if not name or utf16_len(name) > MAX_BUTTON_TEXT:
        await update.effective_message.reply_text(
            f"Use a button name of 1–{MAX_BUTTON_TEXT} units; some symbols count as two."
        )
        return
    context.user_data[K_DRAFT] = {"text": name}
    context.user_data[K_STATE] = S_BTN_LINK
    await reply(
        update,
        f"<b>🌐 Link for “{esc(name)}”</b>\nSend a website URL or @channelname.\n\n<i>/back to return.</i>",
    )


async def on_button_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = normalize_url(update.effective_message.text or "")
    if not url:
        await update.effective_message.reply_text(
            "Use a valid link, such as https://example.com or @channelname."
        )
        return
    draft = context.user_data.get(K_DRAFT)
    if not draft or not draft.get("text"):
        return await ask_button(update, context)
    draft["url"] = url
    context.user_data[K_STATE] = S_BTN_COLOR
    await reply(update, "🎨 Choose a button colour.", color_keyboard())


async def on_button_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    color = COLOR_BY_LABEL.get(norm(update.effective_message.text or ""))
    if not color:
        await update.effective_message.reply_text(
            "Choose a colour below, or use /back.", reply_markup=color_keyboard()
        )
        return
    draft = context.user_data.get(K_DRAFT) or {}
    if draft.get("items"):
        items = [{**item, "color": color} for item in draft["items"]]
    elif draft.get("text") and draft.get("url"):
        items = [{"text": draft["text"], "url": draft["url"], "color": color}]
    else:
        return await ask_button(update, context)
    candidate = deepcopy(get_post(context))
    candidate.buttons.extend(items)
    await save_candidate(update, context, candidate)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    text = (update.effective_message.text or "").strip()
    state = context.user_data.get(K_STATE)
    if state is None:
        if norm(text) == norm(BTN_CREATE):
            return await start_create(update, context)
        await reply(
            update,
            "Tap <b>✨ Create Post</b> to begin, or /help for every feature.",
            main_keyboard(),
        )
        return
    if state == S_MENU:
        action = {
            "text": ask_text,
            "button": ask_button,
            "preview": show_preview,
            "finish": finish,
        }.get(MENU_ACTIONS.get(norm(text)) or "")
        if action:
            return await action(update, context)
        if MENU_ACTIONS.get(norm(text)) == "remove":
            post = deepcopy(get_post(context))
            if post.buttons:
                post.buttons.pop()
            return await save_candidate(update, context, post)
        if extract_media(update.effective_message)[0]:
            return await on_content(update, context)
        quick = parse_quick_buttons(text) if text else None
        if quick:
            context.user_data[K_STATE] = S_BTN_NAME
            return await on_button_name(update, context)
        return await panel(
            update,
            context,
            "Choose an action below, or send new media to replace it."
            + tip("Send <code>Label - link</code> here to add a button instantly."),
        )
    if state in (S_MEDIA, S_TEXT):
        if state == S_TEXT and not update.effective_message.text:
            await update.effective_message.reply_text(
                "Send text to replace the current text, or use /back."
            )
            return
        return await on_content(update, context)
    action = {
        S_BTN_NAME: on_button_name,
        S_BTN_LINK: on_button_link,
        S_BTN_COLOR: on_button_color,
    }.get(state)
    if action:
        return await action(update, context)
    await cmd_back(update, context)


# ----- templates ----------------------------------------------------------
async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Nothing to save yet. Create a post first with /new.")
        return
    name = clean_name(" ".join(context.args or [])) or clean_name(post.default_name())
    try:
        post_id, updated = await get_store(context).save_post(
            update.effective_user.id, name, post.to_dict()
        )
    except StoreError as error:
        if str(error) == "limit":
            text = f"📦 You already have {MAX_SAVED_POSTS} saved posts. Delete one from /posts first."
        else:
            logger.warning("Save failed (%s)", error)
            text = "☁️ Saving failed. Your draft is still here — try again in a moment."
        await reply(update, text)
        return
    verb = "updated" if updated else "saved"
    await reply(
        update,
        f"💾 <b>{esc(name)}</b> {verb}.\nOpen it any time with /open_{post_id}."
        + tip("Saved posts survive restarts. /posts lists them all."),
    )


def describe(row: dict[str, Any]) -> str:
    post = Post.from_dict(row.get("post"))
    return esc(post.summary()) if post else "⚠️ unreadable"


async def cmd_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        rows = await get_store(context).list_posts(update.effective_user.id)
    except StoreError as error:
        logger.warning("List failed (%s)", error)
        await reply(update, "☁️ Couldn't load saved posts right now. Try again soon.")
        return
    if not rows:
        await reply(
            update,
            "<b>💾 Saved posts</b>\n"
            f"{LINE}\nNothing saved yet."
            + tip("While editing a draft, send /save <i>name</i> to keep it."),
        )
        return
    lines = [f"<b>💾 Saved posts</b>  {len(rows)}/{MAX_SAVED_POSTS}", LINE]
    for index, row in enumerate(rows, 1):
        lines.append(
            f"{index}. <b>{esc(row['name'])}</b>\n"
            f"    <i>{describe(row)}</i>\n"
            f"    /open_{row['id']}  ·  /del_{row['id']}"
        )
    await reply(update, "\n".join(lines) + tip("Open loads a copy into the editor."))


async def on_open_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    match = OPEN_DEL_RE.match((update.effective_message.text or "").strip())
    if not match:
        return await unknown_command(update, context)
    action, post_id = match.group(1), int(match.group(2))
    store, user_id = get_store(context), update.effective_user.id
    try:
        if action == "del":
            removed = await store.delete_post(user_id, post_id)
            await reply(
                update,
                "🗑 Saved post deleted." if removed else "🔍 That saved post doesn't exist.",
            )
            return
        row = await store.get_post(user_id, post_id)
    except StoreError as error:
        logger.warning("Template %s failed (%s)", action, error)
        await reply(update, "☁️ Storage is unavailable right now. Try again soon.")
        return
    post = Post.from_dict(row.get("post")) if row else None
    if not post:
        await reply(update, "🔍 That saved post doesn't exist.")
        return
    reset(context)
    context.user_data[K_POST] = post
    await show_preview(update, context)


# ----- publishing & settings ------------------------------------------------
def parse_channel(raw: str) -> str | None:
    value = raw.strip()
    if value.startswith("https://t.me/") or value.startswith("t.me/"):
        value = "@" + value.rsplit("/", 1)[-1]
    return value if CHANNEL_RE.match(value) else None


async def cmd_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    arg = " ".join(context.args or []).strip()
    if not arg:
        profile = await safe_store(context, "get_profile", user_id, default={}) or {}
        current = profile.get("default_channel")
        await reply(
            update,
            "<b>📣 Channel</b>\n"
            f"{LINE}\n"
            + (f"Current: <b>{esc(current)}</b>\n\n" if current else "No channel set.\n\n")
            + "Set one: <code>/channel @mychannel</code>\nRemove: <code>/channel off</code>"
            + tip("Add this bot as an admin with ‘Post messages’ permission first."),
        )
        return
    if arg.lower() in ("off", "none", "remove", "clear"):
        await safe_store(context, "update_profile", user_id, default_channel=None)
        await reply(update, "📣 Channel removed.")
        return
    channel = parse_channel(arg)
    if not channel:
        await reply(update, "Use a channel like <code>@mychannel</code> or its -100… ID.")
        return
    try:
        chat = await context.bot.get_chat(channel)
        if chat.type not in (ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP):
            raise BadRequest("not a channel")
        member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if member.status not in ("administrator", "creator"):
            raise Forbidden("not admin")
    except TelegramError:
        await reply(
            update,
            f"⚠️ I can't post in {esc(channel)} yet.\n"
            "Add me as an <b>admin</b> with ‘Post messages’ permission, then try again.",
        )
        return
    await safe_store(context, "update_profile", user_id, default_channel=channel)
    title = esc(getattr(chat, "title", None) or channel)
    await reply(
        update,
        f"✅ Channel set to <b>{title}</b>.\nUse /publish to post your draft there.",
    )


async def cmd_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Nothing to publish yet. Create a post first with /new.")
        return
    arg = " ".join(context.args or []).strip()
    if arg:
        target = parse_channel(arg)
        if not target:
            await reply(update, "Use a channel like <code>@mychannel</code>.")
            return
    else:
        profile = await safe_store(
            context, "get_profile", update.effective_user.id, default={}
        ) or {}
        target = profile.get("default_channel")
        if not target:
            await reply(
                update,
                "📣 No channel set. Use <code>/channel @mychannel</code> first, "
                "or <code>/publish @mychannel</code>.",
            )
            return
    try:
        message = await post.send(context.bot, target)
    except (BadRequest, Forbidden) as error:
        logger.warning("Publish failed (%s)", type(error).__name__)
        await panel(
            update,
            context,
            f"⚠️ I couldn't post to {esc(target)}. Make sure I'm an admin with "
            "‘Post messages’ permission. Your draft is saved.",
        )
        return
    except TelegramError as error:
        return await panel(update, context, delivery_error(error))
    reset(context)
    count = await record_delivery(update, context)
    link = ""
    if message and isinstance(target, str) and target.startswith("@"):
        link = f"\n🔗 https://t.me/{target[1:]}/{message.message_id}"
    await reply(
        update,
        f"<b>🚀 Published to {esc(target)}</b>{link}"
        + (f"\n\n🏆 That's post <b>#{count}</b>!" if count else ""),
        main_keyboard(),
    )


async def cmd_linkpreview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new, then toggle link previews.")
        return
    candidate = deepcopy(post)
    candidate.link_preview = not candidate.link_preview
    await reply(
        update,
        "🔗 Link preview " + ("<b>on</b>." if candidate.link_preview else "<b>off</b>."),
    )
    await save_candidate(update, context, candidate)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    profile = await safe_store(context, "get_profile", user.id, default={}) or {}
    saved = await safe_store(context, "list_posts", user.id, default=None)
    store = get_store(context)
    post = context.user_data.get(K_POST)
    draft = (
        esc(post.summary()) if isinstance(post, Post) and not post.is_empty() else "none"
    )
    await reply(
        update,
        f"<b>📊 Your stats</b>\n{LINE}\n"
        f"🆔 <code>{user.id}</code>\n"
        f"📝 Posts created: <b>{int(profile.get('posts_created') or 0)}</b>\n"
        f"💾 Saved templates: <b>{len(saved) if saved is not None else '—'}</b>"
        f" / {MAX_SAVED_POSTS}\n"
        f"📣 Channel: <b>{esc(profile.get('default_channel') or 'not set')}</b>\n"
        f"✏️ Draft: {draft}\n"
        f"☁️ Storage: {'Cloud sync' if store.name == 'supabase' else 'This session only'}",
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Use /help for commands, or /back to return to your draft."
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update failed (%s)", type(context.error).__name__)
    if isinstance(context.error, Forbidden):
        return
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "This action could not be completed. Use /back to return to your draft."
            )
        except TelegramError:
            pass


COMMANDS = (
    ("start", cmd_start, "Open Post Maker"),
    ("new", start_create, "Create a new post"),
    ("preview", show_preview, "Preview your draft"),
    ("save", cmd_save, "Save draft as a template"),
    ("posts", cmd_posts, "Your saved posts"),
    ("publish", cmd_publish, "Post to your channel"),
    ("channel", cmd_channel, "Set your channel"),
    ("linkpreview", cmd_linkpreview, "Toggle link preview"),
    ("stats", cmd_stats, "Your stats"),
    ("back", cmd_back, "Return to your draft"),
    ("cancel", cmd_cancel, "Discard your draft"),
    ("help", cmd_help, "Quick guide"),
)


def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    user_msgs = private & ~filters.StatusUpdate.ALL
    app.add_handler(MessageHandler(user_msgs, before_update), group=-1)
    for name, action, _ in COMMANDS:
        app.add_handler(CommandHandler(name, action, private))
    app.add_handler(MessageHandler(private & filters.Regex(OPEN_DEL_RE), on_open_delete))
    app.add_handler(MessageHandler(private & filters.COMMAND, unknown_command))
    app.add_handler(MessageHandler(user_msgs & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(user_msgs, after_update), group=1)
    app.add_error_handler(on_error)
