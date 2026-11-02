"""Private-chat post editor."""

from __future__ import annotations

import logging
from copy import deepcopy

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
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
    extract_media,
    normalize_url,
)

logger = logging.getLogger(__name__)
BTN_CREATE, BTN_TEXT, BTN_BUTTON = "Create Post", "Edit Text", "Add Button"
BTN_PREVIEW, BTN_DONE, BTN_REMOVE = "Preview", "Finish", "Remove Last Button"
COLOR_BY_LABEL = {label: key for key, (label, _) in COLORS.items()}
K_POST, K_STATE, K_DRAFT = "post", "state", "draft_button"
S_MEDIA, S_MENU, S_TEXT = "media", "menu", "text"
S_BTN_NAME, S_BTN_LINK, S_BTN_COLOR = "btn_name", "btn_link", "btn_color"
NO_KEYBOARD = ReplyKeyboardRemove()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_CREATE, style="primary")]],
        resize_keyboard=True,
        input_field_placeholder="Create your next post",
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
        rows.append([KeyboardButton(BTN_REMOVE)])
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, input_field_placeholder="Refine your post"
    )


def color_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(label, style=style) for label, style in COLORS.values()]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_post(context: ContextTypes.DEFAULT_TYPE) -> Post:
    return context.user_data.setdefault(K_POST, Post())


def reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()


async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=choice_keyboard(get_post(context))
    )


def delivery_error(error: TelegramError) -> str:
    if isinstance(error, RetryAfter):
        delay = error.retry_after
        seconds = (
            int(delay.total_seconds())
            if hasattr(delay, "total_seconds")
            else int(delay)
        )
        return f"Telegram is busy. Wait {max(1, seconds)} seconds before retrying. Your draft is saved."
    if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
        return "Delivery could not be confirmed. Your draft is saved. Check the chat before retrying to avoid duplicates."
    return "Telegram could not send this post. Your draft is saved. Edit the content or remove the last button and try again."


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
    await panel(
        update,
        context,
        "<b>Preview</b>\nRefine the text, add a link or finish your post.\n\n<i>/cancel discards this draft.</i>",
    )


async def save_candidate(
    update: Update, context: ContextTypes.DEFAULT_TYPE, candidate: Post
) -> None:
    try:
        candidate.validate()
    except ValueError as error:
        await update.effective_message.reply_text(str(error))
        return
    context.user_data[K_POST] = candidate
    context.user_data.pop(K_DRAFT, None)
    await show_preview(update, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context)
    await update.effective_message.reply_text(
        "<b>Post Maker</b>\n<i>Compose. Refine. Share.</i>\n\n"
        "Create polished posts with text, media and link buttons. Everything happens here in chat.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context)
    context.user_data[K_STATE] = S_MEDIA
    await update.effective_message.reply_text(
        "<b>New post</b>\nSend text, a photo, video, GIF or sticker.\n\n<i>/cancel to exit.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=NO_KEYBOARD,
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context)
    await update.effective_message.reply_text(
        "Draft discarded. Start fresh whenever you're ready.",
        reply_markup=main_keyboard(),
    )


async def cmd_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(K_DRAFT, None)
    if get_post(context).is_empty():
        return await start_create(update, context)
    context.user_data[K_STATE] = S_MENU
    await panel(update, context, "<b>Your draft</b>\nChoose what to refine next.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "<b>Quick guide</b>\n/new — Start a new post\n/preview — View the current draft\n"
        "/back — Leave the current step\n/cancel — Discard the draft\n\n"
        "Use Telegram's text formatting when composing. Send new media from the editor to replace it. "
        "Edit Text replaces the full text. Stickers and long captions are sent as separate messages; forward both.",
        parse_mode=ParseMode.HTML,
    )


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[K_STATE] = S_TEXT
    await update.effective_message.reply_text(
        "<b>Edit text</b>\nSend the complete replacement text. Telegram formatting is preserved.\n\n<i>/back to keep the current text.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=NO_KEYBOARD,
    )


async def ask_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(get_post(context).buttons) >= MAX_BUTTONS:
        return await panel(
            update, context, f"Your post already has {MAX_BUTTONS} buttons."
        )
    context.user_data[K_STATE] = S_BTN_NAME
    context.user_data[K_DRAFT] = {}
    await update.effective_message.reply_text(
        "<b>Button label</b>\nChoose a short name, such as Join Channel.\n\n<i>/back to return.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=NO_KEYBOARD,
    )


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    post = get_post(context)
    if post.is_empty():
        return await start_create(update, context)
    try:
        await post.send(context.bot, update.effective_chat.id)
    except TelegramError as error:
        logger.warning("Final delivery failed (%s)", type(error).__name__)
        return await panel(update, context, delivery_error(error))
    reset(context)
    await update.effective_message.reply_text(
        "<b>Ready to share</b>\nForward the post above to your channel or group. "
        "If the text was sent separately from the media, forward both messages.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


async def on_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, candidate = update.effective_message, deepcopy(get_post(context))
    media_type, file_id = extract_media(msg)
    if media_type:
        candidate.media_type, candidate.file_id = media_type, file_id
        if msg.caption is not None:
            candidate.text = msg.caption_html
    elif msg.text and context.user_data.get(K_STATE) in (S_MEDIA, S_TEXT):
        candidate.text = msg.text_html
    else:
        await msg.reply_text(
            "Send text, a photo, video, GIF or sticker. Use /back to return."
        )
        return
    await save_candidate(update, context, candidate)


async def on_button_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = (update.effective_message.text or "").strip()
    if not name or len(name.encode("utf-16-le")) // 2 > MAX_BUTTON_TEXT:
        await update.effective_message.reply_text(
            f"Use a button name of 1–{MAX_BUTTON_TEXT} units; some symbols count as two."
        )
        return
    context.user_data[K_DRAFT] = {"text": name}
    context.user_data[K_STATE] = S_BTN_LINK
    await update.effective_message.reply_text(
        "<b>Button link</b>\nSend a website URL or @channelname.\n\n<i>/back to return.</i>",
        parse_mode=ParseMode.HTML,
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
    await update.effective_message.reply_text(
        "Choose a button colour.", reply_markup=color_keyboard()
    )


async def on_button_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    color = COLOR_BY_LABEL.get((update.effective_message.text or "").strip())
    if not color:
        await update.effective_message.reply_text(
            "Choose a colour below, or use /back.", reply_markup=color_keyboard()
        )
        return
    draft = context.user_data.get(K_DRAFT) or {}
    if not draft.get("text") or not draft.get("url"):
        return await ask_button(update, context)
    candidate = deepcopy(get_post(context))
    candidate.buttons.append({**draft, "color": color})
    await save_candidate(update, context, candidate)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    text = (update.effective_message.text or "").strip()
    state = context.user_data.get(K_STATE)
    if state is None:
        if text == BTN_CREATE:
            return await start_create(update, context)
        await update.effective_message.reply_text(
            "Choose Create Post to begin.", reply_markup=main_keyboard()
        )
        return
    if state == S_MENU:
        action = {
            BTN_TEXT: ask_text,
            BTN_BUTTON: ask_button,
            BTN_PREVIEW: show_preview,
            BTN_DONE: finish,
        }.get(text)
        if action:
            return await action(update, context)
        if text == BTN_REMOVE:
            post = deepcopy(get_post(context))
            if post.buttons:
                post.buttons.pop()
            return await save_candidate(update, context, post)
        if extract_media(update.effective_message)[0]:
            return await on_content(update, context)
        return await panel(
            update, context, "Choose an action below, or send new media to replace it."
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


def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    for name, action in (
        ("start", cmd_start),
        ("new", start_create),
        ("cancel", cmd_cancel),
        ("back", cmd_back),
        ("preview", show_preview),
        ("help", cmd_help),
    ):
        app.add_handler(CommandHandler(name, action, private))
    app.add_handler(MessageHandler(private & filters.COMMAND, unknown_command))
    app.add_handler(
        MessageHandler(
            private & ~filters.COMMAND & ~filters.StatusUpdate.ALL, on_message
        )
    )
    app.add_error_handler(on_error)
