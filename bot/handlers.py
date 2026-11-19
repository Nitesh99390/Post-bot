from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from copy import deepcopy
from typing import Any

from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    Message,
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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .post import (
    COLORS,
    MAX_BUTTON_TEXT,
    MAX_BUTTONS,
    MAX_COLUMNS,
    Post,
    delete_quietly,
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

K_POST, K_STATE, K_DRAFT, K_HISTORY = "post", "state", "draft_button", "history"
K_PANEL_ID = "panel_id"
K_PREVIEW_IDS = "preview_ids"
K_PREVIEW_META = "preview_meta"

S_MEDIA, S_MENU, S_TEXT = "media", "menu", "text"
S_BTN_NAME, S_BTN_LINK, S_BTN_COLOR = "btn_name", "btn_link", "btn_color"
S_OPTIONS, S_BUTTONS = "options", "buttons"

ALL_STATES = (
    S_MEDIA,
    S_MENU,
    S_TEXT,
    S_BTN_NAME,
    S_BTN_LINK,
    S_BTN_COLOR,
    S_OPTIONS,
    S_BUTTONS,
)

MAX_HISTORY = 10
NO_KEYBOARD = ReplyKeyboardRemove()
LINE = "━━━━━━━━━━━━━━"
CHANNEL_RE = re.compile(r"^(@[A-Za-z][A-Za-z0-9_]{3,31}|-100\d{5,})$")
OPEN_DEL_RE = re.compile(r"^/(open|del)_(\d{1,12})(?:@\w+)?$")


def norm(text: str) -> str:
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


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CREATE, style="primary")]],
        resize_keyboard=True,
        input_field_placeholder="Tap Create Post or drop media/text ✨",
    )


def choice_keyboard(post: Post) -> InlineKeyboardMarkup:
    return studio_keyboard(post)


def color_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label, callback_data=f"st:clr:{key}", style=style)
                for key, (label, style) in COLORS.items()
            ],
            [InlineKeyboardButton("‹ Back", callback_data="st:back")],
        ]
    )


def cancel_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✖ Cancel", callback_data="st:cancel")]]
    )


def back_inline_keyboard(*, clear_part: str | None = None) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    if clear_part:
        row.append(
            InlineKeyboardButton(
                f"🧹 Clear {clear_part}",
                callback_data=f"st:rm:{clear_part}",
                style="danger",
            )
        )
    row.append(InlineKeyboardButton("‹ Back", callback_data="st:back"))
    return InlineKeyboardMarkup([row])


def studio_keyboard(
    post: Post, *, channel: str | None = None, has_undo: bool = False
) -> InlineKeyboardMarkup:
    has_text = bool(post.plain_text())
    row1: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            "✏️ Edit Text" if has_text else "✏️ Add Text",
            callback_data="st:text",
        )
    ]
    if len(post.buttons) < MAX_BUTTONS:
        row1.append(InlineKeyboardButton("🔗 Add Button", callback_data="st:btn"))

    rows: list[list[InlineKeyboardButton]] = [row1]

    manage_row: list[InlineKeyboardButton] = []
    if post.buttons:
        manage_row.append(
            InlineKeyboardButton(
                f"🎛 Buttons ({len(post.buttons)})", callback_data="st:btns"
            )
        )
    manage_row.append(InlineKeyboardButton("⚙️ Options", callback_data="st:opts"))
    if has_undo:
        manage_row.append(InlineKeyboardButton("↩️ Undo", callback_data="st:undo"))
    rows.append(manage_row)

    finish_row: list[InlineKeyboardButton] = [
        InlineKeyboardButton("✅ Finish", callback_data="st:done", style="success")
    ]
    if channel:
        finish_row.append(
            InlineKeyboardButton(
                f"🚀 Publish", callback_data="st:pub", style="primary"
            )
        )
    rows.append(finish_row)

    rows.append(
        [
            InlineKeyboardButton("💾 Save", callback_data="st:save"),
            InlineKeyboardButton("🗑 Discard", callback_data="st:cancel", style="danger"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def buttons_manager_keyboard(post: Post) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    color_emoji = {"blue": "🔵", "green": "🟢", "red": "🔴"}
    for idx, btn in enumerate(post.buttons):
        dot = color_emoji.get(btn.get("color", "blue"), "🔵")
        label = btn["text"]
        short = label[:20] + "…" if len(label) > 21 else label
        rows.append(
            [
                InlineKeyboardButton(
                    f"{dot} {idx + 1}. {short}", callback_data=f"st:bcol:{idx}"
                ),
                InlineKeyboardButton(
                    "🗑", callback_data=f"st:bdel:{idx}", style="danger"
                ),
            ]
        )
    ctrl_row: list[InlineKeyboardButton] = []
    if len(post.buttons) < MAX_BUTTONS:
        ctrl_row.append(
            InlineKeyboardButton("➕ Add Button", callback_data="st:btn", style="primary")
        )
    if len(post.buttons) > 1:
        ctrl_row.append(
            InlineKeyboardButton(
                f"📐 {post.columns}/row", callback_data="st:lay"
            )
        )
    if ctrl_row:
        rows.append(ctrl_row)
    action_row: list[InlineKeyboardButton] = []
    if post.buttons:
        action_row.append(
            InlineKeyboardButton(
                "🧹 Clear All", callback_data="st:rm:buttons", style="danger"
            )
        )
    action_row.append(InlineKeyboardButton("‹ Back to Studio", callback_data="st:back"))
    rows.append(action_row)
    return InlineKeyboardMarkup(rows)


def options_keyboard(post: Post) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row_a: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            f"🔗 Preview: {'ON' if post.link_preview else 'OFF'}",
            callback_data="st:tog:lp",
        ),
        InlineKeyboardButton(
            f"📐 Grid: {post.columns}/row",
            callback_data="st:lay",
        ),
    ]
    rows.append(row_a)

    if post.supports_spoiler() or post.supports_caption_above():
        media_row: list[InlineKeyboardButton] = []
        if post.supports_spoiler():
            media_row.append(
                InlineKeyboardButton(
                    f"🫣 Spoiler: {'ON' if post.spoiler else 'OFF'}",
                    callback_data="st:tog:sp",
                )
            )
        if post.supports_caption_above():
            media_row.append(
                InlineKeyboardButton(
                    f"⬆️ Caption: {'Top' if post.caption_above else 'Bottom'}",
                    callback_data="st:tog:cap",
                )
            )
        rows.append(media_row)

    rows.append(
        [
            InlineKeyboardButton(
                f"🛡 Protect: {'ON' if post.protect else 'OFF'}",
                callback_data="st:tog:prot",
            ),
            InlineKeyboardButton(
                f"🔕 Silent: {'ON' if post.silent else 'OFF'}",
                callback_data="st:tog:sil",
            ),
        ]
    )

    clear_row: list[InlineKeyboardButton] = []
    if post.plain_text():
        clear_row.append(
            InlineKeyboardButton("🧹 Text", callback_data="st:rm:text", style="danger")
        )
    if post.media_type:
        clear_row.append(
            InlineKeyboardButton("🧹 Media", callback_data="st:rm:media", style="danger")
        )
    if post.buttons:
        clear_row.append(
            InlineKeyboardButton(
                "🧹 Buttons", callback_data="st:rm:buttons", style="danger"
            )
        )
    if clear_row:
        rows.append(clear_row)

    rows.append([InlineKeyboardButton("‹ Back to Studio", callback_data="st:back")])
    return InlineKeyboardMarkup(rows)


def get_post(context: ContextTypes.DEFAULT_TYPE) -> Post:
    return context.user_data.setdefault(K_POST, Post())


def reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()


def pop_workspace_ids(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    ids: list[int] = []
    panel_id = context.user_data.pop(K_PANEL_ID, None)
    if isinstance(panel_id, int):
        ids.append(panel_id)
    prev_ids = context.user_data.pop(K_PREVIEW_IDS, None)
    if isinstance(prev_ids, list):
        ids.extend(mid for mid in prev_ids if isinstance(mid, int))
    context.user_data.pop(K_PREVIEW_META, None)
    return ids


async def clear_workspace(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    keep_preview: bool = False,
) -> None:
    panel_id = context.user_data.pop(K_PANEL_ID, None)
    ids: list[int] = [panel_id] if isinstance(panel_id, int) else []
    if not keep_preview:
        prev_ids = context.user_data.pop(K_PREVIEW_IDS, None)
        if isinstance(prev_ids, list):
            ids.extend(mid for mid in prev_ids if isinstance(mid, int))
        context.user_data.pop(K_PREVIEW_META, None)
    if ids:
        await delete_quietly(context.bot, chat_id, ids)


async def cleanup_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if msg and chat and not update.callback_query:
        await delete_quietly(context.bot, chat.id, [msg.message_id])


def push_history(context: ContextTypes.DEFAULT_TYPE, previous: Post) -> None:
    if previous.is_empty():
        return
    stack: list[dict[str, Any]] = context.user_data.setdefault(K_HISTORY, [])
    snap = previous.to_dict()
    if stack and stack[-1] == snap:
        return
    stack.append(snap)
    if len(stack) > MAX_HISTORY:
        del stack[:-MAX_HISTORY]


def get_store(context: ContextTypes.DEFAULT_TYPE):
    store = context.bot_data.get("store")
    if store is None:
        store = context.bot_data["store"] = MemoryStore()
    return store


async def safe_store(context, method: str, *args, default=None, **kwargs):
    try:
        return await getattr(get_store(context), method)(*args, **kwargs)
    except StoreError as error:
        logger.warning("Storage %s failed (%s)", method, error)
        return default


def esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def tip(text: str) -> str:
    return f"\n\n<i>💡 {text}</i>"


async def reply(update: Update, text: str, markup=None) -> Message:
    chat_id = update.effective_chat.id
    if update.callback_query:
        return await update.get_bot().send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    return await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=markup
    )


async def upsert_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    reposition: bool = False,
) -> Message:
    """Edit the single Studio control panel in place, or create/reposition it cleanly."""
    chat_id = update.effective_chat.id
    panel_id = context.user_data.get(K_PANEL_ID)
    if isinstance(panel_id, int) and not reposition:
        try:
            edited = await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=panel_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            if isinstance(edited, Message):
                return edited
        except BadRequest as error:
            if "message is not modified" in str(error).lower():
                return update.effective_message
            panel_id = None
        except TelegramError:
            panel_id = None

    old_panel = context.user_data.pop(K_PANEL_ID, None)
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        disable_notification=True,
    )
    context.user_data[K_PANEL_ID] = sent.message_id
    if isinstance(old_panel, int) and old_panel != sent.message_id:
        await delete_quietly(context.bot, chat_id, [old_panel])
    return sent


async def default_channel_for(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> str | None:
    profile = await safe_store(context, "get_profile", user_id, default={}) or {}
    return profile.get("default_channel")


def has_history(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get(K_HISTORY))


async def panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reposition: bool = False,
) -> None:
    post = get_post(context)
    channel = await default_channel_for(context, update.effective_user.id)
    kb = studio_keyboard(post, channel=channel, has_undo=has_history(context))
    await upsert_panel(update, context, text, kb, reposition=reposition)


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


def serialize(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    data: dict[str, Any] = {}
    post = context.user_data.get(K_POST)
    if isinstance(post, Post) and not post.is_empty():
        data["post"] = post.to_dict()
    for key in (K_STATE, K_DRAFT, K_PANEL_ID, K_PREVIEW_IDS, K_PREVIEW_META):
        if context.user_data.get(key) is not None:
            data[key] = context.user_data[key]
    history = context.user_data.get(K_HISTORY)
    if isinstance(history, list) and history and "post" in data:
        data[K_HISTORY] = history[-MAX_HISTORY:]
    return data


def restore(context: ContextTypes.DEFAULT_TYPE, data: Any) -> None:
    if not isinstance(data, dict):
        return
    post = Post.from_dict(data.get("post"))
    if post:
        context.user_data[K_POST] = post
    state = data.get(K_STATE)
    if state in ALL_STATES:
        context.user_data[K_STATE] = state
    if isinstance(data.get(K_DRAFT), dict):
        context.user_data[K_DRAFT] = data[K_DRAFT]
    if type(data.get(K_PANEL_ID)) is int:
        context.user_data[K_PANEL_ID] = data[K_PANEL_ID]
    raw_prev_ids = data.get(K_PREVIEW_IDS)
    if isinstance(raw_prev_ids, list) and all(type(x) is int for x in raw_prev_ids):
        context.user_data[K_PREVIEW_IDS] = list(raw_prev_ids)
    if isinstance(data.get(K_PREVIEW_META), dict):
        context.user_data[K_PREVIEW_META] = data[K_PREVIEW_META]
    raw_history = data.get(K_HISTORY)
    if isinstance(raw_history, list) and post:
        valid = [
            item
            for item in raw_history[-MAX_HISTORY:]
            if Post.from_dict(item) is not None
        ]
        if valid:
            context.user_data[K_HISTORY] = valid


async def before_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if not update.callback_query:
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
        res = await safe_store(context, "save_session", user.id, data, default=False)
        if res is False:
            return
    else:
        res = await safe_store(context, "delete_session", user.id, default=False)
        if res is False:
            return
    hashes[user.id] = digest


def draft_header(post: Post, title: str = "🎛 Post Studio") -> str:
    return f"<b>{title}</b>\n<code>{esc(post.summary())}</code>\n{LINE}\n"


def studio_body(post: Post, *, notice: str | None = None) -> str:
    header = draft_header(post, "🎛 Post Studio")
    banner = f"{notice}\n\n" if notice else ""
    hint = (
        "Text is sent separately with this media — forward both when sharing."
        if post.splits_text()
        else "Drop new media or <code>Label - link</code> anytime to update live."
    )
    return (
        header
        + banner
        + "Live preview is above — refine anything below or finish."
        + tip(hint)
    )


async def show_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    notice: str | None = None,
    force_resend: bool = False,
) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    chat_id = update.effective_chat.id
    prev_ids: list[int] = (
        [] if force_resend else list(context.user_data.get(K_PREVIEW_IDS) or [])
    )
    prev_meta: dict[str, Any] | None = (
        None if force_resend else context.user_data.get(K_PREVIEW_META)
    )
    if force_resend and context.user_data.get(K_PREVIEW_IDS):
        await delete_quietly(
            context.bot, chat_id, list(context.user_data.get(K_PREVIEW_IDS) or [])
        )
        context.user_data.pop(K_PREVIEW_IDS, None)
        context.user_data.pop(K_PREVIEW_META, None)

    try:
        new_ids, new_meta = await post.sync_preview(
            context.bot, chat_id, prev_ids, prev_meta
        )
    except TelegramError as error:
        logger.warning("Preview failed (%s)", type(error).__name__)
        context.user_data[K_STATE] = S_MENU
        await panel(update, context, delivery_error(error))
        return False

    repositioned = new_ids != prev_ids
    context.user_data[K_PREVIEW_IDS] = new_ids
    context.user_data[K_PREVIEW_META] = new_meta
    context.user_data[K_STATE] = S_MENU

    view = context.user_data.pop("_return_view", None)
    if view == S_OPTIONS:
        context.user_data[K_STATE] = S_OPTIONS
        text = (
            draft_header(post, "⚙️ Post Options")
            + (f"{notice}\n\n" if notice else "")
            + "Toggle settings — your preview above updates live."
        )
        await upsert_panel(
            update, context, text, options_keyboard(post), reposition=repositioned
        )
        return
    if view == S_BUTTONS and post.buttons:
        context.user_data[K_STATE] = S_BUTTONS
        text = (
            draft_header(post, "🎛 Manage Buttons")
            + (f"{notice}\n\n" if notice else "")
            + "Tap a button to cycle its colour (🔵 → 🟢 → 🔴), or 🗑 to delete it."
        )
        await upsert_panel(
            update,
            context,
            text,
            buttons_manager_keyboard(post),
            reposition=repositioned,
        )
        return

    await panel(
        update,
        context,
        studio_body(post, notice=notice),
        reposition=repositioned,
    )


async def save_candidate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    candidate: Post,
    *,
    notice: str | None = None,
) -> bool:
    try:
        candidate.validate()
    except ValueError as error:
        err_text = f"⚠️ {esc(error)}"
        if context.user_data.get(K_PANEL_ID):
            state = context.user_data.get(K_STATE)
            kb = (
                cancel_inline_keyboard()
                if state == S_MEDIA
                else back_inline_keyboard()
            )
            await upsert_panel(update, context, err_text, kb)
        else:
            await reply(update, err_text)
        return False
    current = get_post(context)
    if candidate != current:
        push_history(context, current)
    context.user_data[K_POST] = candidate
    context.user_data.pop(K_DRAFT, None)
    ok = await show_preview(update, context, notice=notice)
    return ok is not False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    post = context.user_data.get(K_POST)
    history = context.user_data.get(K_HISTORY)
    panel_id = context.user_data.get(K_PANEL_ID)
    preview_ids = context.user_data.get(K_PREVIEW_IDS)
    preview_meta = context.user_data.get(K_PREVIEW_META)
    has_draft = isinstance(post, Post) and not post.is_empty()
    reset(context)
    if has_draft:
        context.user_data[K_POST] = post
        if history:
            context.user_data[K_HISTORY] = history
        if panel_id:
            context.user_data[K_PANEL_ID] = panel_id
        if preview_ids:
            context.user_data[K_PREVIEW_IDS] = preview_ids
        if preview_meta:
            context.user_data[K_PREVIEW_META] = preview_meta
    profile = await safe_store(context, "get_profile", user.id, default={}) or {}
    saved = await safe_store(context, "list_posts", user.id, default=[]) or []
    created = int(profile.get("posts_created") or 0)
    channel = profile.get("default_channel")
    text = (
        "<b>✨ Post Studio</b>\n<i>Zero-clutter · Live Preview · Instant Publish</i>\n"
        f"{LINE}\n"
        f"Hi {esc(user.first_name or 'there')}! Send any media, text, or forwarded post "
        "and watch it update live in a single clean workspace.\n\n"
        f"📝 Posts created: <b>{created}</b>  ·  💾 Saved: <b>{len(saved)}</b>"
        + (f"\n📣 Channel: <b>{esc(channel)}</b>" if channel else "")
    )
    if has_draft:
        text += tip("You have an active draft — /back to open Studio.")
    else:
        text += tip("Tap ✨ Create Post or drop media directly · /help for all features.")
    await reply(update, text, main_keyboard())


async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await cleanup_user_message(update, context)
    await clear_workspace(context, chat_id)
    reset(context)
    context.user_data[K_STATE] = S_MEDIA
    prompt_text = (
        "<b>✨ New Post Studio</b>\n"
        f"{LINE}\n"
        "Send <b>text</b>, <b>photo</b>, <b>video</b>, <b>GIF</b>, <b>sticker</b>, <b>audio</b> or <b>file</b>.\n\n"
        "↪️ Or <b>forward</b> any post to import its media, formatting &amp; link buttons."
        + tip("Everything edits live in one place — zero chat clutter.")
    )
    await upsert_panel(update, context, prompt_text, cancel_inline_keyboard())


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await cleanup_user_message(update, context)
    await clear_workspace(context, chat_id)
    reset(context)
    await reply(
        update,
        "🗑 Draft discarded. Tap <b>✨ Create Post</b> whenever you're ready.",
        main_keyboard(),
    )


async def cmd_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cleanup_user_message(update, context)
    context.user_data.pop(K_DRAFT, None)
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    context.user_data[K_STATE] = S_MENU
    if not context.user_data.get(K_PREVIEW_IDS):
        return await show_preview(update, context)
    await panel(update, context, studio_body(post))


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cleanup_user_message(update, context)
    stack: list[dict[str, Any]] = context.user_data.get(K_HISTORY) or []
    while stack:
        restored = Post.from_dict(stack.pop())
        if restored and not restored.is_empty():
            context.user_data[K_POST] = restored
            context.user_data.pop(K_DRAFT, None)
            return await show_preview(update, context, notice="↩️ <i>Reverted last change.</i>")
    if context.user_data.get(K_PANEL_ID) and not get_post(context).is_empty():
        await panel(update, context, studio_body(get_post(context), notice="📭 <i>Nothing to undo.</i>"))
    else:
        await reply(update, "📭 Nothing to undo right now.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(
        update,
        "<b>📖 Post Studio Guide</b>\n"
        f"{LINE}\n"
        "<b>Zero-Clutter Live Editor</b>\n"
        "• Drop text, media, or forward any post to start.\n"
        "• Your preview updates <b>in-place</b> — no repeated messages!\n"
        "• Use inline buttons below the preview for everything.\n\n"
        "<b>Fast Button Shortcuts</b>\n"
        "• Single: <code>Join Channel - @mychannel</code>\n"
        "• Side-by-side: <code>Join - @chan &amp;&amp; Website | example.com</code>\n"
        "• Multi-row: send multiple lines at once!\n\n"
        "<b>Commands</b>\n"
        "/new — Start a fresh post\n"
        "/preview — Refresh live workspace\n"
        "/posts — Open or manage saved templates\n"
        "/save <i>name</i> — Save current draft\n"
        "/channel <i>@name</i> — Link default channel\n"
        "/publish <i>[pin]</i> — Publish directly (optional pin)\n"
        "/stats — View your creator stats\n"
        "/cancel — Discard active draft",
    )


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    context.user_data[K_STATE] = S_TEXT
    has_text = bool(post.plain_text())
    await upsert_panel(
        update,
        context,
        draft_header(post, "✏️ Edit Text" if has_text else "✏️ Add Text")
        + "Send your text message now. Bold, italic, spoilers, quotes &amp; links are preserved."
        + tip("Your message will automatically merge into the live preview above."),
        back_inline_keyboard(clear_part="text" if has_text else None),
    )


async def ask_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if len(post.buttons) >= MAX_BUTTONS:
        return await panel(
            update,
            context,
            studio_body(post, notice=f"🔒 <i>Maximum {MAX_BUTTONS} buttons reached.</i>"),
        )
    context.user_data[K_STATE] = S_BTN_NAME
    context.user_data[K_DRAFT] = {}
    await upsert_panel(
        update,
        context,
        draft_header(post, f"🔗 Add Button ({len(post.buttons) + 1}/{MAX_BUTTONS})")
        + "Send the <b>button label</b> (e.g. <i>Join Channel</i>)."
        + tip(
            "Pro shortcut: send <code>Label - link</code> directly, or join with <code>&amp;&amp;</code> for side-by-side rows!"
        ),
        back_inline_keyboard(),
    )


async def show_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    context.user_data[K_STATE] = S_OPTIONS
    await upsert_panel(
        update,
        context,
        draft_header(post, "⚙️ Post Options")
        + "Tap any setting below to toggle it live.",
        options_keyboard(post),
    )


async def show_buttons_manager(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    if not post.buttons:
        return await ask_button(update, context)
    context.user_data[K_STATE] = S_BUTTONS
    await upsert_panel(
        update,
        context,
        draft_header(post, "🎛 Manage Buttons")
        + "Tap a button to cycle colour (🔵 → 🟢 → 🔴), or tap 🗑 to remove it.",
        buttons_manager_keyboard(post),
    )


async def record_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    return await safe_store(context, "increment_posts", update.effective_user.id)


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    chat_id = update.effective_chat.id

    prev_ids: list[int] = list(context.user_data.get(K_PREVIEW_IDS) or [])
    # Reuse the clean live preview already sitting in chat unless content protection is active
    reused_existing = bool(prev_ids and not post.protect)
    if not reused_existing:
        try:
            await post.send(context.bot, chat_id)
        except TelegramError as error:
            logger.warning("Final delivery failed (%s)", type(error).__name__)
            return await panel(update, context, delivery_error(error))

    await cleanup_user_message(update, context)
    split = post.splits_text()
    protected = post.protect
    await clear_workspace(context, chat_id, keep_preview=reused_existing)
    reset(context)

    count = await record_delivery(update, context)
    channel = await default_channel_for(context, update.effective_user.id)
    if protected:
        text = (
            "<b>🎉 Post ready (Protected)</b>\n"
            "Forwarding protection is active — use /publish next time to send protected posts straight to a channel."
        )
    else:
        text = (
            "<b>✅ Ready to share</b> — forward the post above!"
            + (" <i>(Forward both messages)</i>" if split else "")
        )
    if count:
        text += f"  ·  🏆 Post <b>#{count}</b>"
    if channel:
        text += f"\n<i>💡 Next time tap 🚀 Publish to post straight to {esc(channel)}.</i>"
    else:
        text += "\n<i>💡 Link a channel once with /channel @name for 1-tap publishing.</i>"
    await reply(update, text, main_keyboard())


async def on_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, candidate = update.effective_message, deepcopy(get_post(context))
    media_type, file_id = extract_media(msg)
    state = context.user_data.get(K_STATE)
    if media_type:
        candidate.media_type, candidate.file_id = media_type, file_id
        if getattr(msg, "has_media_spoiler", False) and candidate.supports_spoiler():
            candidate.spoiler = True
        elif not candidate.supports_spoiler():
            candidate.spoiler = False
        if not candidate.supports_caption_above():
            candidate.caption_above = False
        if msg.caption is not None:
            candidate.text = msg.caption_html
    elif msg.text and state in (S_MEDIA, S_TEXT):
        candidate.text = msg.text_html
    else:
        await cleanup_user_message(update, context)
        kb = cancel_inline_keyboard() if state == S_MEDIA else back_inline_keyboard()
        await upsert_panel(
            update,
            context,
            "⚠️ Send text, a photo, video, GIF, sticker, audio or file.",
            kb,
        )
        return
    if state == S_MEDIA or getattr(msg, "forward_origin", None) is not None:
        imported = extract_buttons(msg)
        if imported:
            candidate.buttons = imported
    # Validate and sync preview BEFORE deleting the user's message so if delivery fails, nothing is lost
    saved = await save_candidate(update, context, candidate)
    if saved:
        await cleanup_user_message(update, context)


async def on_button_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.effective_message.text or ""
    await cleanup_user_message(update, context)
    post = get_post(context)
    quick = parse_quick_buttons(raw)
    if quick:
        free = MAX_BUTTONS - len(post.buttons)
        if len(quick) > free:
            await upsert_panel(
                update,
                context,
                draft_header(post, "🔗 Add Button")
                + f"⚠️ Only <b>{free}</b> more button(s) fit in this post. Send fewer buttons.",
                back_inline_keyboard(),
            )
            return
        context.user_data[K_DRAFT] = {"items": quick}
        context.user_data[K_STATE] = S_BTN_COLOR
        names = ", ".join(esc(b["text"]) for b in quick)
        await upsert_panel(
            update,
            context,
            draft_header(post, "🎨 Button Colour")
            + f"Pick a colour for <b>{names}</b>:",
            color_keyboard(),
        )
        return
    name = raw.strip()
    if not name or utf16_len(name) > MAX_BUTTON_TEXT:
        await upsert_panel(
            update,
            context,
            draft_header(post, "🔗 Add Button")
            + f"⚠️ Use a button name of 1–{MAX_BUTTON_TEXT} characters.",
            back_inline_keyboard(),
        )
        return
    context.user_data[K_DRAFT] = {"text": name}
    context.user_data[K_STATE] = S_BTN_LINK
    await upsert_panel(
        update,
        context,
        draft_header(post, f"🌐 Link for “{esc(name)}”")
        + "Send a website URL (e.g. <code>example.com</code>) or <code>@channelname</code>.",
        back_inline_keyboard(),
    )


async def on_button_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_link = update.effective_message.text or ""
    await cleanup_user_message(update, context)
    post = get_post(context)
    url = normalize_url(raw_link)
    if not url:
        draft_name = esc((context.user_data.get(K_DRAFT) or {}).get("text") or "Button")
        await upsert_panel(
            update,
            context,
            draft_header(post, f"🌐 Link for “{draft_name}”")
            + "⚠️ Invalid link. Send a valid URL like <code>https://example.com</code> or <code>@channelname</code>.",
            back_inline_keyboard(),
        )
        return
    draft = context.user_data.get(K_DRAFT)
    if not draft or not draft.get("text"):
        return await ask_button(update, context)
    draft["url"] = url
    context.user_data[K_STATE] = S_BTN_COLOR
    await upsert_panel(
        update,
        context,
        draft_header(post, "🎨 Button Colour")
        + f"Choose a style for <b>{esc(draft['text'])}</b> ({esc(url)}):",
        color_keyboard(),
    )


async def apply_button_color(
    update: Update, context: ContextTypes.DEFAULT_TYPE, color: str
) -> None:
    draft = context.user_data.get(K_DRAFT) or {}
    if draft.get("items"):
        items = [{**item, "color": color} for item in draft["items"]]
    elif draft.get("text") and draft.get("url"):
        items = [{"text": draft["text"], "url": draft["url"], "color": color}]
    else:
        return await ask_button(update, context)
    candidate = deepcopy(get_post(context))
    candidate.buttons.extend(items)
    added_label = (
        f"{len(items)} buttons" if len(items) > 1 else f"“{esc(items[0]['text'])}”"
    )
    await save_candidate(
        update, context, candidate, notice=f"✅ <i>Added {added_label}.</i>"
    )


async def on_button_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_color = update.effective_message.text or ""
    await cleanup_user_message(update, context)
    color = COLOR_BY_LABEL.get(norm(raw_color))
    if not color:
        post = get_post(context)
        await upsert_panel(
            update,
            context,
            draft_header(post, "🎨 Button Colour")
            + "Tap a colour button below:",
            color_keyboard(),
        )
        return
    await apply_button_color(update, context, color)


async def remove_last_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = deepcopy(get_post(context))
    if post.buttons:
        post.buttons.pop()
    if post.is_empty():
        push_history(context, get_post(context))
        await clear_workspace(context, update.effective_chat.id)
        context.user_data[K_POST] = Post()
        context.user_data[K_STATE] = S_MEDIA
        await upsert_panel(
            update,
            context,
            "↩️ Removed the last button. Your draft is now empty — send text or media to continue.",
            cancel_inline_keyboard(),
        )
        return
    await save_candidate(
        update, context, post, notice="↩️ <i>Removed last button.</i>"
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    msg = update.effective_message
    text = (msg.text or "").strip()
    state = context.user_data.get(K_STATE)
    if state is None:
        if norm(text) == norm(BTN_CREATE):
            return await start_create(update, context)
        if extract_media(msg)[0] or getattr(msg, "forward_origin", None) is not None:
            reset(context)
            context.user_data[K_STATE] = S_MEDIA
            return await on_content(update, context)
        await reply(
            update,
            "Tap <b>✨ Create Post</b> or send media directly to begin · /help for guide.",
            main_keyboard(),
        )
        return
    if state in (S_MENU, S_OPTIONS, S_BUTTONS):
        if norm(text) == norm(BTN_CREATE):
            return await start_create(update, context)
        mapped = MENU_ACTIONS.get(norm(text))
        if mapped:
            if mapped != "finish":
                await cleanup_user_message(update, context)
            if mapped == "text":
                return await ask_text(update, context)
            if mapped == "button":
                return await ask_button(update, context)
            if mapped == "preview":
                return await show_preview(update, context, force_resend=True)
            if mapped == "finish":
                return await finish(update, context)
            if mapped == "remove":
                return await remove_last_button(update, context)
        if extract_media(msg)[0] or getattr(msg, "forward_origin", None) is not None:
            return await on_content(update, context)
        quick = parse_quick_buttons(text) if text else None
        if quick:
            context.user_data[K_STATE] = S_BTN_NAME
            return await on_button_name(update, context)
        await cleanup_user_message(update, context)
        return await panel(
            update,
            context,
            studio_body(
                get_post(context),
                notice="💡 <i>Use the buttons below, drop new media, or send <code>Label - link</code>.</i>",
            ),
        )
    if state in (S_MEDIA, S_TEXT):
        if state == S_TEXT and not msg.text:
            await cleanup_user_message(update, context)
            await upsert_panel(
                update,
                context,
                draft_header(get_post(context), "✏️ Edit Text")
                + "⚠️ Send text to update the caption/body, or tap Back.",
                back_inline_keyboard(
                    clear_part="text" if get_post(context).plain_text() else None
                ),
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


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not query.data:
        return
    data = query.data
    post = get_post(context)

    async def ack(toast: str | None = None, *, alert: bool = False) -> None:
        try:
            await query.answer(text=toast, show_alert=alert)
        except TelegramError:
            pass

    if data == "st:new":
        await ack()
        return await start_create(update, context)

    if data == "st:cancel":
        await ack("Draft discarded")
        return await cmd_cancel(update, context)

    if data.startswith("tpl:"):
        parts = data.split(":")
        if len(parts) == 3 and parts[2].isdigit():
            act, pid = parts[1], int(parts[2])
            await handle_template_callback(update, context, query, act, pid)
            return
        await ack()
        return

    if post.is_empty() and data not in ("st:cancel", "st:new"):
        await ack("No active draft — starting a new post.")
        return await start_create(update, context)

    if data == "st:back":
        await ack()
        context.user_data.pop(K_DRAFT, None)
        context.user_data[K_STATE] = S_MENU
        if not context.user_data.get(K_PREVIEW_IDS):
            return await show_preview(update, context)
        return await panel(update, context, studio_body(post))

    if data == "st:text":
        await ack()
        return await ask_text(update, context)

    if data == "st:btn":
        await ack()
        return await ask_button(update, context)

    if data == "st:opts":
        await ack()
        return await show_options(update, context)

    if data == "st:btns":
        await ack()
        return await show_buttons_manager(update, context)

    if data == "st:undo":
        stack: list[dict[str, Any]] = context.user_data.get(K_HISTORY) or []
        while stack:
            restored = Post.from_dict(stack.pop())
            if restored and not restored.is_empty():
                await ack("Reverted last change")
                context.user_data[K_POST] = restored
                context.user_data.pop(K_DRAFT, None)
                return await show_preview(
                    update, context, notice="↩️ <i>Reverted last change.</i>"
                )
        await ack("Nothing to undo")
        return

    if data == "st:done":
        await ack("Post ready!")
        return await finish(update, context)

    if data == "st:pub":
        await ack("Publishing…")
        return await publish_draft(update, context, pin=False)

    if data == "st:save":
        name = clean_name(post.default_name())
        try:
            post_id, updated = await get_store(context).save_post(
                update.effective_user.id, name, post.to_dict()
            )
        except StoreError as error:
            if str(error) == "limit":
                await ack(f"Limit reached ({MAX_SAVED_POSTS}). Delete one in /posts.", alert=True)
            else:
                await ack("Cloud save failed — try again.", alert=True)
            return
        verb = "Updated" if updated else "Saved"
        await ack(f"💾 {verb}: {name}")
        return await panel(
            update,
            context,
            studio_body(
                post,
                notice=f"💾 <b>{esc(name)}</b> {verb.lower()}! (/open_{post_id} · /posts)",
            ),
        )

    if data.startswith("st:clr:"):
        color = data.split(":", 2)[2]
        if color in COLORS:
            await ack(f"Selected {COLORS[color][0]}")
            return await apply_button_color(update, context, color)
        await ack()
        return

    if data == "st:lay":
        candidate = deepcopy(post)
        candidate.columns = (candidate.columns % MAX_COLUMNS) + 1
        if candidate.columns > 1:
            for b in candidate.buttons:
                b.pop("same_row", None)
        return_view = context.user_data.get(K_STATE)
        if return_view in (S_OPTIONS, S_BUTTONS):
            context.user_data["_return_view"] = return_view
        await ack(f"Grid: {candidate.columns} per row")
        await save_candidate(
            update,
            context,
            candidate,
            notice=f"📐 <i>Layout: {candidate.columns} button(s) per row.</i>",
        )
        return

    if data.startswith("st:tog:"):
        flag = data.split(":", 2)[2]
        candidate = deepcopy(post)
        label = ""
        if flag == "lp":
            candidate.link_preview = not candidate.link_preview
            label = f"Link preview {'ON' if candidate.link_preview else 'OFF'}"
        elif flag == "sp":
            if not candidate.supports_spoiler():
                await ack("Spoiler works on photos, videos & GIFs", alert=True)
                return
            candidate.spoiler = not candidate.spoiler
            label = f"Media spoiler {'ON' if candidate.spoiler else 'OFF'}"
        elif flag == "cap":
            if not candidate.supports_caption_above():
                await ack("Top caption works on photos, videos & GIFs", alert=True)
                return
            candidate.caption_above = not candidate.caption_above
            label = f"Caption {'above' if candidate.caption_above else 'below'} media"
        elif flag == "prot":
            candidate.protect = not candidate.protect
            label = f"Protection {'ON' if candidate.protect else 'OFF'}"
        elif flag == "sil":
            candidate.silent = not candidate.silent
            label = f"Silent mode {'ON' if candidate.silent else 'OFF'}"
        else:
            await ack()
            return
        context.user_data["_return_view"] = S_OPTIONS
        await ack(label)
        await save_candidate(update, context, candidate, notice=f"⚙️ <i>{label}.</i>")
        return

    if data.startswith("st:bcol:"):
        idx_str = data.split(":", 2)[2]
        if idx_str.isdigit():
            idx = int(idx_str)
            if 0 <= idx < len(post.buttons):
                order = ["blue", "green", "red"]
                candidate = deepcopy(post)
                cur = candidate.buttons[idx].get("color", "blue")
                nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "blue"
                candidate.buttons[idx]["color"] = nxt
                context.user_data["_return_view"] = S_BUTTONS
                await ack(f"Colour: {COLORS[nxt][0]}")
                await save_candidate(update, context, candidate)
                return
        await ack()
        return

    if data.startswith("st:bdel:"):
        idx_str = data.split(":", 2)[2]
        if idx_str.isdigit():
            idx = int(idx_str)
            if 0 <= idx < len(post.buttons):
                candidate = deepcopy(post)
                removed_btn = candidate.buttons.pop(idx)
                if candidate.is_empty():
                    push_history(context, post)
                    await clear_workspace(context, update.effective_chat.id)
                    context.user_data[K_POST] = Post()
                    context.user_data[K_STATE] = S_MEDIA
                    await ack("Button removed")
                    await upsert_panel(
                        update,
                        context,
                        "🧹 Removed button. Draft is now empty — send text or media to continue.",
                        cancel_inline_keyboard(),
                    )
                    return
                if candidate.buttons:
                    context.user_data["_return_view"] = S_BUTTONS
                await ack(f"Removed {removed_btn['text']}")
                await save_candidate(
                    update,
                    context,
                    candidate,
                    notice=f"🗑 <i>Removed “{esc(removed_btn['text'])}”.</i>",
                )
                return
        await ack()
        return

    if data.startswith("st:rm:"):
        part = data.split(":", 2)[2]
        await ack()
        await clear_part_action(update, context, part)
        return

    await ack()


async def handle_template_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: CallbackQuery,
    action: str,
    post_id: int,
) -> None:
    store, user_id = get_store(context), update.effective_user.id
    try:
        if action == "del":
            removed = await store.delete_post(user_id, post_id)
            await query.answer("🗑 Template deleted" if removed else "Not found")
            rows = await store.list_posts(user_id)
            text, kb = render_posts_list(rows)
            try:
                await query.edit_message_text(
                    text, parse_mode=ParseMode.HTML, reply_markup=kb
                )
            except TelegramError:
                pass
            return
        if action == "open":
            row = await store.get_post(user_id, post_id)
            loaded = Post.from_dict(row.get("post")) if row else None
            if not loaded:
                await query.answer("Template not found", show_alert=True)
                return
            await query.answer(f"Opened: {row['name']}")
            await clear_workspace(context, update.effective_chat.id)
            if query.message:
                await delete_quietly(
                    context.bot, update.effective_chat.id, [query.message.message_id]
                )
            reset(context)
            context.user_data[K_POST] = loaded
            await show_preview(
                update,
                context,
                notice=f"📂 <i>Loaded template <b>{esc(row['name'])}</b>.</i>",
            )
            return
    except StoreError:
        await query.answer("Cloud storage unavailable right now.", show_alert=True)


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
    await cleanup_user_message(update, context)
    verb = "updated" if updated else "saved"
    msg_text = f"💾 <b>{esc(name)}</b> {verb} (/open_{post_id})."
    if context.user_data.get(K_PANEL_ID):
        await panel(update, context, studio_body(post, notice=msg_text))
    else:
        await reply(
            update,
            f"💾 <b>{esc(name)}</b> {verb}.\nOpen it any time with /open_{post_id}."
            + tip("Saved posts survive restarts. /posts lists them all."),
        )


def describe(row: dict[str, Any]) -> str:
    post = Post.from_dict(row.get("post"))
    return esc(post.summary()) if post else "⚠️ unreadable"


def render_posts_list(
    rows: list[dict[str, Any]],
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not rows:
        return (
            "<b>💾 Saved Templates</b>\n"
            f"{LINE}\nNothing saved yet."
            + tip("Tap 💾 Save inside Post Studio or use /save <i>name</i>."),
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("✨ Create Post", callback_data="st:new", style="primary")]]
            ),
        )
    lines = [f"<b>💾 Saved Templates</b>  {len(rows)}/{MAX_SAVED_POSTS}", LINE]
    kb_rows: list[list[InlineKeyboardButton]] = []
    for index, row in enumerate(rows, 1):
        lines.append(
            f"{index}. <b>{esc(row['name'])}</b> — <i>{describe(row)}</i>\n"
            f"    /open_{row['id']}  ·  /del_{row['id']}"
        )
        if index <= 8:
            short = row["name"][:18] + "…" if len(row["name"]) > 19 else row["name"]
            kb_rows.append(
                [
                    InlineKeyboardButton(
                        f"📂 {index}. {short}", callback_data=f"tpl:open:{row['id']}"
                    ),
                    InlineKeyboardButton(
                        "🗑", callback_data=f"tpl:del:{row['id']}", style="danger"
                    ),
                ]
            )
    return (
        "\n".join(lines) + tip("Tap 📂 below to load straight into Studio."),
        InlineKeyboardMarkup(kb_rows) if kb_rows else None,
    )


async def cmd_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        rows = await get_store(context).list_posts(update.effective_user.id)
    except StoreError as error:
        logger.warning("List failed (%s)", error)
        await reply(update, "☁️ Couldn't load saved posts right now. Try again soon.")
        return
    text, kb = render_posts_list(rows)
    await reply(update, text, kb)


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
    await cleanup_user_message(update, context)
    await clear_workspace(context, update.effective_chat.id)
    reset(context)
    context.user_data[K_POST] = post
    await show_preview(
        update,
        context,
        notice=f"📂 <i>Opened template <b>{esc(row['name'])}</b>.</i>",
    )


def parse_channel(raw: str) -> str | None:
    value = raw.strip()
    value = re.sub(r"^(?:https?://)?t\.me/", "@", value, flags=re.IGNORECASE)
    if value.startswith("@"):
        value = "@" + value[1:].split("/", 1)[0].split("?", 1)[0]
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
        if (
            chat.type == ChatType.CHANNEL
            and member.status == "administrator"
            and getattr(member, "can_post_messages", True) is False
        ):
            raise Forbidden("cannot post")
        user_member = await context.bot.get_chat_member(chat.id, user_id)
        if user_member.status not in ("administrator", "creator"):
            await reply(
                update,
                f"⚠️ Only admins of {esc(channel)} can link or publish to it.",
            )
            return
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
        f"✅ Channel set to <b>{title}</b>.\nYou now have a 1-tap <b>🚀 Publish</b> button inside Post Studio!",
    )


async def publish_draft(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    arg: str = "",
    pin: bool = False,
) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Nothing to publish yet. Create a post first with /new.")
        return
    user_id = update.effective_user.id
    if arg:
        target = parse_channel(arg)
        if not target:
            await reply(update, "Use a channel like <code>@mychannel</code>.")
            return
        try:
            user_member = await context.bot.get_chat_member(target, user_id)
        except (BadRequest, Forbidden) as error:
            logger.warning("Publish check failed (%s)", type(error).__name__)
            await panel(
                update,
                context,
                f"⚠️ I couldn't post to {esc(target)}. Make sure I'm an admin with "
                "‘Post messages’ permission. Your draft is saved.",
            )
            return
        except TelegramError as error:
            return await panel(update, context, delivery_error(error))
        if user_member.status not in ("administrator", "creator"):
            await reply(
                update,
                f"⚠️ Only admins of {esc(target)} can publish to it.",
            )
            return
    else:
        target = await default_channel_for(context, user_id)
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
    pinned_note = ""
    if pin and message:
        try:
            await context.bot.pin_chat_message(
                target, message.message_id, disable_notification=post.silent
            )
            pinned_note = "\n📌 Pinned in channel."
        except TelegramError:
            pinned_note = "\n<i>⚠️ Published, but missing permission to pin.</i>"
    await cleanup_user_message(update, context)
    await clear_workspace(context, update.effective_chat.id)
    reset(context)
    count = await record_delivery(update, context)
    link = ""
    if message and isinstance(target, str) and target.startswith("@"):
        link = f"\n🔗 https://t.me/{target[1:]}/{message.message_id}"
    await reply(
        update,
        f"<b>🚀 Published to {esc(target)}</b>{link}{pinned_note}"
        + (f"\n\n🏆 That's post <b>#{count}</b>!" if count else ""),
        main_keyboard(),
    )


async def cmd_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tokens = [t for t in (context.args or []) if t.strip()]
    pin = False
    remaining: list[str] = []
    for tok in tokens:
        if tok.lower() in ("pin", "--pin", "-p"):
            pin = True
        else:
            remaining.append(tok)
    arg = " ".join(remaining).strip()
    await publish_draft(update, context, arg=arg, pin=pin)


async def cmd_linkpreview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new, then toggle link previews.")
        return
    await cleanup_user_message(update, context)
    candidate = deepcopy(post)
    candidate.link_preview = not candidate.link_preview
    state_txt = "on" if candidate.link_preview else "off"
    await save_candidate(
        update, context, candidate, notice=f"🔗 Link preview <b>{state_txt}</b>."
    )


async def cmd_layout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new, then set the button layout.")
        return
    arg = " ".join(context.args or []).strip().lower()
    candidate = deepcopy(post)
    if not arg:
        candidate.columns = (candidate.columns % MAX_COLUMNS) + 1
    elif arg in ("1", "2", "3"):
        candidate.columns = int(arg)
    elif arg in ("auto", "custom"):
        candidate.columns = 1
    else:
        await reply(
            update,
            "Use <code>/layout 1</code>, <code>/layout 2</code> or <code>/layout 3</code> to set buttons per row.",
        )
        return
    if arg in ("1", "2", "3") and int(arg) > 1:
        for b in candidate.buttons:
            b.pop("same_row", None)
    await cleanup_user_message(update, context)
    await save_candidate(
        update,
        context,
        candidate,
        notice=f"📐 Button layout set to <b>{candidate.columns} per row</b>.",
    )


async def cmd_spoiler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new.")
        return
    if not post.supports_spoiler():
        await reply(
            update,
            "🫣 Spoiler blur works on photos, videos and GIFs. Attach one first.",
        )
        return
    await cleanup_user_message(update, context)
    candidate = deepcopy(post)
    candidate.spoiler = not candidate.spoiler
    await save_candidate(
        update,
        context,
        candidate,
        notice="🫣 Media spoiler " + ("<b>on</b>." if candidate.spoiler else "<b>off</b>."),
    )


async def cmd_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new.")
        return
    if not post.supports_caption_above():
        await reply(
            update,
            "⬆️ Top captions are supported on photos, videos and GIFs.",
        )
        return
    await cleanup_user_message(update, context)
    candidate = deepcopy(post)
    candidate.caption_above = not candidate.caption_above
    pos = "above media" if candidate.caption_above else "below media"
    await save_candidate(
        update, context, candidate, notice=f"⬆️ Caption position: <b>{pos}</b>."
    )


async def cmd_protect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new.")
        return
    await cleanup_user_message(update, context)
    candidate = deepcopy(post)
    candidate.protect = not candidate.protect
    await save_candidate(
        update,
        context,
        candidate,
        notice="🛡 Content protection "
        + ("<b>on</b> (forwarding &amp; saving blocked)." if candidate.protect else "<b>off</b>."),
    )


async def cmd_silent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Create a post first with /new.")
        return
    await cleanup_user_message(update, context)
    candidate = deepcopy(post)
    candidate.silent = not candidate.silent
    await save_candidate(
        update,
        context,
        candidate,
        notice="🔕 Silent delivery " + ("<b>on</b>." if candidate.silent else "<b>off</b>."),
    )


async def clear_part_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE, part: str
) -> None:
    post = get_post(context)
    candidate = deepcopy(post)
    if part == "text":
        if not candidate.plain_text():
            await reply(update, "ℹ️ This draft has no text to clear.")
            return
        candidate.text = ""
        candidate.caption_above = False
    elif part == "media":
        if not candidate.media_type:
            await reply(update, "ℹ️ This draft has no media to clear.")
            return
        candidate.media_type = None
        candidate.file_id = None
        candidate.spoiler = False
        candidate.caption_above = False
    elif part == "buttons":
        if not candidate.buttons:
            await reply(update, "ℹ️ This draft has no buttons to clear.")
            return
        candidate.buttons = []
        candidate.columns = 1
    else:
        await reply(
            update,
            "Specify what to clear:\n"
            "• <code>/clear text</code> — Remove text/caption\n"
            "• <code>/clear media</code> — Remove attached media\n"
            "• <code>/clear buttons</code> — Remove all link buttons",
        )
        return

    await cleanup_user_message(update, context)
    if candidate.is_empty():
        push_history(context, post)
        await clear_workspace(context, update.effective_chat.id)
        context.user_data[K_POST] = Post()
        context.user_data[K_STATE] = S_MEDIA
        await upsert_panel(
            update,
            context,
            f"🧹 Cleared {part}. Your draft is now empty — send new content or /undo.",
            cancel_inline_keyboard(),
        )
        return
    await save_candidate(
        update, context, candidate, notice=f"🧹 Cleared <b>{part}</b>."
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        await reply(update, "📭 Your draft is already empty.")
        return
    part = " ".join(context.args or []).strip().lower()
    await clear_part_action(update, context, part)


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
    if isinstance(update, Update):
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Action could not be completed. Try /back.", show_alert=True
                )
            except TelegramError:
                pass
        elif update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "This action could not be completed. Use /back to return to your draft."
                )
            except TelegramError:
                pass


async def cmd_preview_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cleanup_user_message(update, context)
    await show_preview(update, context, force_resend=True)


COMMANDS = (
    ("start", cmd_start, "Open Post Studio"),
    ("new", start_create, "Create a new post"),
    ("preview", cmd_preview_refresh, "Refresh live preview"),
    ("undo", cmd_undo, "Undo last draft change"),
    ("clear", cmd_clear, "Clear text, media or buttons"),
    ("layout", cmd_layout, "Set buttons per row (1-3)"),
    ("spoiler", cmd_spoiler, "Toggle media spoiler blur"),
    ("caption", cmd_caption, "Place caption above or below"),
    ("protect", cmd_protect, "Block forwarding and saving"),
    ("silent", cmd_silent, "Toggle silent notification"),
    ("linkpreview", cmd_linkpreview, "Toggle link preview"),
    ("save", cmd_save, "Save draft as a template"),
    ("posts", cmd_posts, "Your saved posts"),
    ("publish", cmd_publish, "Post to your channel"),
    ("channel", cmd_channel, "Set your channel"),
    ("stats", cmd_stats, "Your stats"),
    ("back", cmd_back, "Return to Post Studio"),
    ("cancel", cmd_cancel, "Discard your draft"),
    ("help", cmd_help, "Quick guide"),
)


def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    user_msgs = private & ~filters.StatusUpdate.ALL

    app.add_handler(MessageHandler(user_msgs, before_update), group=-1)
    app.add_handler(CallbackQueryHandler(before_update), group=-1)

    app.add_handler(CallbackQueryHandler(on_callback))
    for name, action, _ in COMMANDS:
        app.add_handler(CommandHandler(name, action, private))
    app.add_handler(MessageHandler(private & filters.Regex(OPEN_DEL_RE), on_open_delete))
    app.add_handler(MessageHandler(private & filters.COMMAND, unknown_command))
    app.add_handler(MessageHandler(user_msgs & ~filters.COMMAND, on_message))

    app.add_handler(MessageHandler(user_msgs, after_update), group=1)
    app.add_handler(CallbackQueryHandler(after_update), group=1)
    app.add_error_handler(on_error)
