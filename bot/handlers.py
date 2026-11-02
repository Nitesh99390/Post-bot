"""Telegram handlers - one simple, kid-friendly flow.

    ✨ Create Post
        └─ send GIF / Sticker / Emoji / Photo           -> preview
    [📝 Add Text] [🔘 Add Button] [✅ Done]
        ├─ 📝 Add Text   -> keyboard hidden, type text   -> preview
        └─ 🔘 Add Button -> keyboard hidden, button name -> link
                         -> [🔴 Red] [🟢 Green] [🔵 Blue] -> preview
    ✅ Done -> final post (ready to forward) + back to main menu

The Mini App (🎨 Mini App) builds the same post in a colourful page and sends
it back with Telegram.WebApp.sendData().
"""
from __future__ import annotations

import html
import json
import logging

from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import MINI_APP_URL
from .post import (
    COLORS,
    MAX_BUTTON_TEXT,
    MAX_BUTTONS,
    MEDIA_NAMES,
    TEXT_LIMIT,
    Post,
    extract_media,
    normalize_url,
    plain_len,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- labels
BTN_CREATE = "✨ Create Post"
BTN_MINI_APP = "🎨 Mini App"
BTN_TEXT = "📝 Add Text"
BTN_BUTTON = "🔘 Add Button"
BTN_DONE = "✅ Done"
COLOR_BY_LABEL = {label: key for key, (label, _style) in COLORS.items()}

# ---------------------------------------------------------------- states
K_POST, K_STATE, K_DRAFT = "post", "state", "draft_button"
S_MEDIA = "media"  # waiting for GIF / sticker / emoji
S_MENU = "menu"  # showing [Text] [Button] [Done]
S_TEXT = "text"  # waiting for text
S_BTN_NAME = "btn_name"
S_BTN_LINK = "btn_link"
S_BTN_COLOR = "btn_color"


# ====================================================================== keyboards
def main_keyboard() -> ReplyKeyboardMarkup:
    row = [KeyboardButton(BTN_CREATE, style="success")]
    if MINI_APP_URL:
        row.append(KeyboardButton(BTN_MINI_APP, web_app=WebAppInfo(MINI_APP_URL), style="primary"))
    return ReplyKeyboardMarkup([row], resize_keyboard=True, is_persistent=True)


def choice_keyboard(post: Post) -> ReplyKeyboardMarkup:
    first = [KeyboardButton(BTN_TEXT, style="primary")]
    if len(post.buttons) < MAX_BUTTONS:
        first.append(KeyboardButton(BTN_BUTTON, style="primary"))
    return ReplyKeyboardMarkup(
        [first, [KeyboardButton(BTN_DONE, style="success")]],
        resize_keyboard=True,
        input_field_placeholder="Choose what to add 👇",
    )


def color_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(label, style=style) for label, style in COLORS.values()]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Pick a colour 🎨",
    )


NO_KEYBOARD = ReplyKeyboardRemove()


# ====================================================================== helpers
def get_post(context: ContextTypes.DEFAULT_TYPE) -> Post:
    post = context.user_data.get(K_POST)
    if not isinstance(post, Post):
        post = Post()
        context.user_data[K_POST] = post
    return post


def set_state(context: ContextTypes.DEFAULT_TYPE, state: str | None) -> None:
    context.user_data[K_STATE] = state


def reset(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data[K_POST] = Post()
    context.user_data.pop(K_DRAFT, None)
    set_state(context, None)


async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, note: str = "") -> bool:
    """Send the post built so far, then the [Text] [Button] [Done] keyboard.

    Returns False if Telegram refused the post (e.g. a bad button link).
    """
    post = get_post(context)
    chat_id = update.effective_chat.id
    try:
        await post.send(context.bot, chat_id)
    except TelegramError as e:
        logger.info("Preview failed: %s", e)
        return False
    set_state(context, S_MENU)
    text = (note + "\n\n" if note else "") + "👆 <b>Your post so far</b>\nWhat do you want to add next?"
    await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=choice_keyboard(post))
    return True


# ====================================================================== commands / main buttons
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset(context)
    name = html.escape(update.effective_user.first_name or "friend")
    mini = f"\n🎨 Or tap <b>{BTN_MINI_APP}</b> to make it in a colourful app." if MINI_APP_URL else ""
    await update.effective_message.reply_text(
        f"👋 Hi <b>{name}</b>!\n\n"
        "I make beautiful posts with <b>GIF, stickers, emojis, text</b> and "
        "<b>colourful buttons</b> 🌈\n\n"
        f"👇 Tap <b>{BTN_CREATE}</b> to start.{mini}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset(context)
    set_state(context, S_MEDIA)
    await update.effective_message.reply_text(
        "🎬 <b>Step 1</b>\n\nSend me a <b>GIF</b>, <b>Sticker</b> or <b>Emoji</b> 😍\n"
        "<i>(a photo or video also works)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=NO_KEYBOARD,
    )


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(context, S_TEXT)
    await update.effective_message.reply_text(
        "✍️ Type your <b>text</b> and send it.", parse_mode=ParseMode.HTML, reply_markup=NO_KEYBOARD
    )


async def ask_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(get_post(context).buttons) >= MAX_BUTTONS:
        await update.effective_message.reply_text(f"You already have {MAX_BUTTONS} buttons 🙂")
        return
    set_state(context, S_BTN_NAME)
    context.user_data[K_DRAFT] = {}
    await update.effective_message.reply_text(
        "🔘 What should the <b>button say</b>?\n<i>Example: Join Channel</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=NO_KEYBOARD,
    )


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = get_post(context)
    msg = update.effective_message
    if post.is_empty():
        await msg.reply_text("Your post is empty 🙈", reply_markup=main_keyboard())
        reset(context)
        return
    try:
        await post.send(context.bot, msg.chat_id)
    except TelegramError as e:
        await msg.reply_text(f"⚠️ Could not send the post: {html.escape(e.message)}")
        return
    reset(context)
    await msg.reply_text(
        "🎉 <b>Your post is ready!</b>\n\nForward it to any channel or group. "
        f"Tap <b>{BTN_CREATE}</b> to make another one.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# ====================================================================== message router
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = (msg.text or "").strip()
    state = context.user_data.get(K_STATE)

    # Main buttons work at any time
    if text == BTN_CREATE:
        return await start_create(update, context)
    if text == BTN_MINI_APP:  # shown only if Mini App could not open
        return await msg.reply_text("Please open the Mini App with the button below 👇", reply_markup=main_keyboard())

    if state == S_MEDIA:
        return await on_media_step(update, context)
    if state == S_MENU:
        return await on_menu_step(update, context)
    if state == S_TEXT:
        return await on_text_step(update, context)
    if state == S_BTN_NAME:
        return await on_button_name(update, context)
    if state == S_BTN_LINK:
        return await on_button_link(update, context)
    if state == S_BTN_COLOR:
        return await on_button_color(update, context)

    await msg.reply_text(f"👇 Tap <b>{BTN_CREATE}</b> to start.", parse_mode=ParseMode.HTML, reply_markup=main_keyboard())


def _set_media_from(msg, post: Post) -> bool:
    media_type, file_id = extract_media(msg)
    if not media_type:
        return False
    post.media_type, post.file_id = media_type, file_id
    if msg.caption:
        post.text = msg.caption_html
    return True


async def on_media_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, post = update.effective_message, get_post(context)
    if _set_media_from(msg, post):
        await show_preview(update, context, f"✅ {MEDIA_NAMES[post.media_type]} added!")
        return
    if msg.text:
        if plain_len(msg.text_html) > TEXT_LIMIT:
            await msg.reply_text("😅 That is too long. Please send something shorter.")
            return
        post.emoji = msg.text_html
        await show_preview(update, context, "✅ Added!")
        return
    await msg.reply_text("Please send a GIF, sticker or emoji 🙂")


async def on_menu_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, post = update.effective_message, get_post(context)
    text = (msg.text or "").strip()
    if text == BTN_TEXT:
        return await ask_text(update, context)
    if text == BTN_BUTTON:
        return await ask_button(update, context)
    if text == BTN_DONE:
        return await finish(update, context)
    # Sending a GIF / sticker here replaces the media (handy after the Mini App)
    if _set_media_from(msg, post):
        await show_preview(update, context, f"✅ {MEDIA_NAMES[post.media_type]} added!")
        return
    await msg.reply_text("👇 Please choose one of the buttons.", reply_markup=choice_keyboard(post))


async def on_text_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, post = update.effective_message, get_post(context)
    if not msg.text:
        await msg.reply_text("✍️ Please type some text.")
        return
    new_text = msg.text_html
    if plain_len(post.emoji) + plain_len(new_text) > TEXT_LIMIT:
        await msg.reply_text(f"😅 Text is too long (max {TEXT_LIMIT} letters). Please send a shorter one.")
        return
    post.text = new_text
    await show_preview(update, context, "✅ Text added!")


async def on_button_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    name = (msg.text or "").strip()
    if not name:
        await msg.reply_text("Please type the button name 🙂")
        return
    if len(name) > MAX_BUTTON_TEXT:
        await msg.reply_text(f"Too long 😅 Max {MAX_BUTTON_TEXT} letters.")
        return
    context.user_data.setdefault(K_DRAFT, {})["text"] = name
    set_state(context, S_BTN_LINK)
    await msg.reply_text(
        "🔗 Now send the <b>link</b> for this button.\n<i>Example: https://t.me/yourchannel</i>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def on_button_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    url = normalize_url(msg.text or "")
    if not url:
        await msg.reply_text(
            "❌ That is not a link.\nSend it like: <code>https://t.me/yourchannel</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    context.user_data.setdefault(K_DRAFT, {})["url"] = url
    set_state(context, S_BTN_COLOR)
    await msg.reply_text("🎨 Choose the <b>button colour</b>:", parse_mode=ParseMode.HTML, reply_markup=color_keyboard())


async def on_button_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, post = update.effective_message, get_post(context)
    color = COLOR_BY_LABEL.get((msg.text or "").strip())
    draft = context.user_data.get(K_DRAFT) or {}
    if not color:
        await msg.reply_text("👇 Tap a colour.", reply_markup=color_keyboard())
        return
    if not draft.get("text") or not draft.get("url"):  # should not happen, start the button again
        return await ask_button(update, context)
    post.buttons.append({"text": draft["text"], "url": draft["url"], "color": color})
    context.user_data.pop(K_DRAFT, None)
    if not await show_preview(update, context, "✅ Button added!"):
        post.buttons.pop()
        set_state(context, S_BTN_LINK)
        context.user_data[K_DRAFT] = {"text": draft["text"]}
        await msg.reply_text(
            "❌ Telegram did not accept that link. Please send a different link.",
            reply_markup=NO_KEYBOARD,
        )


# ====================================================================== Mini App
def post_from_webapp(raw: str) -> Post:
    """Build a Post from the JSON the Mini App sends. Raises ValueError."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("bad data")
    post = Post(
        emoji=html.escape(str(data.get("emoji") or "").strip())[:200],
        text=html.escape(str(data.get("text") or "").strip())[:TEXT_LIMIT],
    )
    for b in (data.get("buttons") or [])[:MAX_BUTTONS]:
        if not isinstance(b, dict):
            continue
        name = str(b.get("text") or "").strip()[:MAX_BUTTON_TEXT]
        url = normalize_url(str(b.get("url") or ""))
        color = b.get("color") if b.get("color") in COLORS else "blue"
        if name and url:
            post.buttons.append({"text": name, "url": url, "color": color})
    return post


async def on_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    try:
        post = post_from_webapp(msg.web_app_data.data)
    except (ValueError, TypeError):
        await msg.reply_text("⚠️ Something went wrong with the Mini App. Please try again.", reply_markup=main_keyboard())
        return
    if post.is_empty():
        await msg.reply_text("Your post is empty 🙈", reply_markup=main_keyboard())
        return
    context.user_data[K_POST] = post
    context.user_data.pop(K_DRAFT, None)
    ok = await show_preview(
        update, context, "✅ Made in Mini App!\n🎬 Want a GIF or sticker? Just send it now."
    )
    if not ok:
        post.buttons = []
        await show_preview(update, context, "⚠️ A button link was not accepted, so buttons were removed.")


# ====================================================================== errors
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Oops! Something went wrong. Tap /start to try again.")
        except TelegramError:
            pass


# ====================================================================== registration
def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler(["start", "new", "cancel"], cmd_start, private))
    app.add_handler(MessageHandler(private & filters.StatusUpdate.WEB_APP_DATA, on_web_app_data))
    app.add_handler(MessageHandler(private & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
