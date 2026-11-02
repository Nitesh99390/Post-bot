from __future__ import annotations

import html
import logging
from enum import StrEnum

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import texts as T
from .post import (
    COLORS,
    MAX_BUTTON_TEXT,
    MAX_BUTTONS,
    TEXT_LIMIT,
    Button,
    Post,
    extract_media,
    normalize_url,
    plain_len,
)

logger = logging.getLogger(__name__)

K_POST, K_STATE, K_DRAFT, K_HISTORY = "post", "state", "draft", "history"
HISTORY_LIMIT = 20
COLOR_BY_LABEL = {label: key for key, (label, _) in COLORS.items()}
STYLE_BY_LABEL = {label: key for key, (label, _, _) in T.STYLES.items()}


class State(StrEnum):
    IDLE = "idle"
    MEDIA = "media"
    MENU = "menu"
    TEXT = "text"
    STYLE = "style"
    BTN_NAME = "btn_name"
    BTN_LINK = "btn_link"
    BTN_COLOR = "btn_color"


# ---------------------------------------------------------------- keyboards
def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(T.BTN_NEW, style="success"), KeyboardButton(T.BTN_HELP)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def kb_menu(post: Post, can_undo: bool) -> ReplyKeyboardMarkup:
    row1 = [KeyboardButton(T.BTN_TEXT, style="primary")]
    if len(post.buttons) < MAX_BUTTONS:
        row1.append(KeyboardButton(T.BTN_BUTTON, style="primary"))
    row2 = [KeyboardButton(T.BTN_DONE, style="success")]
    if can_undo:
        row2.insert(0, KeyboardButton(T.BTN_UNDO))
    return ReplyKeyboardMarkup(
        [row1, row2, [KeyboardButton(T.BTN_CANCEL, style="danger")]],
        resize_keyboard=True,
        input_field_placeholder="Choose an action",
    )


def kb_cancel(skip: bool = False) -> ReplyKeyboardMarkup:
    row = [KeyboardButton(T.BTN_CANCEL, style="danger")]
    if skip:
        row.insert(0, KeyboardButton(T.BTN_SKIP))
    return ReplyKeyboardMarkup([row], resize_keyboard=True)


def kb_colors() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(label, style=style) for label, style in COLORS.values()],
            [KeyboardButton(T.BTN_CANCEL, style="danger")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Pick a colour",
    )


def kb_styles() -> ReplyKeyboardMarkup:
    labels = [label for label, _, _ in T.STYLES.values()]
    return ReplyKeyboardMarkup(
        [labels[:3], labels[3:], [KeyboardButton(T.BTN_CANCEL, style="danger")]],
        resize_keyboard=True,
        input_field_placeholder="Pick a style",
    )


REMOVE = ReplyKeyboardRemove()


# ---------------------------------------------------------------- session
class Session:
    __slots__ = ("data",)

    def __init__(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.data = context.user_data

    @property
    def post(self) -> Post:
        raw = self.data.get(K_POST)
        if isinstance(raw, Post):
            return raw
        post = Post.from_dict(raw) if isinstance(raw, dict) else Post()
        self.data[K_POST] = post
        return post

    @post.setter
    def post(self, value: Post) -> None:
        self.data[K_POST] = value

    @property
    def state(self) -> State:
        try:
            return State(self.data.get(K_STATE) or State.IDLE)
        except ValueError:
            return State.IDLE

    @state.setter
    def state(self, value: State) -> None:
        self.data[K_STATE] = str(value)

    @property
    def draft(self) -> dict:
        return self.data.setdefault(K_DRAFT, {})

    @property
    def history(self) -> list[dict]:
        return self.data.setdefault(K_HISTORY, [])

    def snapshot(self) -> None:
        hist = self.history
        hist.append(self.post.to_dict())
        del hist[:-HISTORY_LIMIT]

    def undo(self) -> bool:
        hist = self.history
        if not hist:
            return False
        self.post = Post.from_dict(hist.pop())
        return True

    def reset(self) -> None:
        self.data[K_POST] = Post()
        self.data[K_STATE] = str(State.IDLE)
        self.data.pop(K_DRAFT, None)
        self.data.pop(K_HISTORY, None)


async def reply(update: Update, text: str, markup=None, **kwargs) -> None:
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True, **kwargs
    )


async def show_preview(update: Update, s: Session) -> bool:
    chat_id = update.effective_chat.id
    bot = update.get_bot()
    try:
        await s.post.send(bot, chat_id)
    except BadRequest as e:
        logger.info("Preview rejected: %s", e.message)
        return False
    s.state = State.MENU
    await bot.send_message(
        chat_id,
        T.PREVIEW.format(summary=s.post.summary()),
        parse_mode=ParseMode.HTML,
        reply_markup=kb_menu(s.post, bool(s.history)),
    )
    return True


# ---------------------------------------------------------------- commands
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Session(context).reset()
    await reply(update, T.WELCOME.format(new=T.BTN_NEW), kb_main())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = Session(context)
    await reply(update, T.HELP, kb_main() if s.state == State.IDLE else None)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = Session(context)
    s.reset()
    s.state = State.MEDIA
    await reply(update, T.STEP_MEDIA, kb_cancel())


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    Session(context).reset()
    await reply(update, T.CANCELLED.format(new=T.BTN_NEW), kb_main())


# ---------------------------------------------------------------- actions
async def ask_text(update: Update, s: Session) -> None:
    s.state = State.TEXT
    await reply(update, T.ASK_TEXT, kb_cancel())


async def ask_button(update: Update, s: Session) -> None:
    if len(s.post.buttons) >= MAX_BUTTONS:
        await reply(update, T.ERR_MAX_BUTTONS.format(max=MAX_BUTTONS), kb_menu(s.post, bool(s.history)))
        return
    s.state = State.BTN_NAME
    s.data[K_DRAFT] = {}
    await reply(update, T.ASK_BTN_NAME, kb_cancel())


async def undo(update: Update, s: Session) -> None:
    if not s.undo():
        await reply(update, T.NOTHING_TO_UNDO, kb_menu(s.post, False))
        return
    if s.post.is_empty():
        s.state = State.MEDIA
        await reply(update, T.UNDONE, None)
        await reply(update, T.STEP_MEDIA, kb_cancel())
        return
    await reply(update, T.UNDONE, REMOVE)
    await show_preview(update, s)


async def publish(update: Update, s: Session) -> None:
    post = s.post
    if post.is_empty():
        s.reset()
        await reply(update, T.ERR_EMPTY, kb_main())
        return
    try:
        await post.send(update.get_bot(), update.effective_chat.id)
    except BadRequest as e:
        await reply(update, f"⚠️ {html.escape(e.message)}", kb_menu(post, bool(s.history)))
        return
    s.reset()
    await reply(update, T.DONE.format(new=T.BTN_NEW), kb_main())


def apply_media(update: Update, s: Session) -> bool:
    media_type, file_id = extract_media(update.effective_message)
    if not media_type:
        return False
    s.snapshot()
    s.post.media_type, s.post.file_id = media_type, file_id
    caption = update.effective_message.caption_html
    if caption and not s.post.text:
        s.post.text = caption
    return True


# ---------------------------------------------------------------- state steps
async def step_media(update: Update, s: Session) -> None:
    msg = update.effective_message
    if apply_media(update, s):
        await show_preview(update, s)
        return
    if msg.text:
        if plain_len(msg.text_html) > TEXT_LIMIT:
            await reply(update, T.ERR_TOO_LONG.format(limit=TEXT_LIMIT))
            return
        s.snapshot()
        s.post.emoji = msg.text_html
        await show_preview(update, s)
        return
    await reply(update, T.ERR_NEED_MEDIA)


async def step_menu(update: Update, s: Session) -> None:
    text = (update.effective_message.text or "").strip()
    if text == T.BTN_TEXT:
        return await ask_text(update, s)
    if text == T.BTN_BUTTON:
        return await ask_button(update, s)
    if text == T.BTN_UNDO:
        return await undo(update, s)
    if text == T.BTN_DONE:
        return await publish(update, s)
    if apply_media(update, s):
        await show_preview(update, s)
        return
    await reply(update, T.ERR_PICK, kb_menu(s.post, bool(s.history)))


async def step_text(update: Update, s: Session) -> None:
    msg = update.effective_message
    if not msg.text:
        await reply(update, T.ERR_NEED_TEXT)
        return
    if plain_len(s.post.emoji) + plain_len(msg.text_html) > TEXT_LIMIT:
        await reply(update, T.ERR_TOO_LONG.format(limit=TEXT_LIMIT))
        return
    s.draft["text"] = msg.text_html
    s.state = State.STYLE
    await reply(update, T.ASK_STYLE, kb_styles())


async def step_style(update: Update, s: Session) -> None:
    label = (update.effective_message.text or "").strip()
    style = STYLE_BY_LABEL.get(label)
    if style is None:
        await reply(update, T.ERR_PICK, kb_styles())
        return
    raw = s.draft.get("text")
    if not raw:
        return await ask_text(update, s)
    _, open_tag, close_tag = T.STYLES[style]
    s.snapshot()
    s.post.text = f"{open_tag}{raw}{close_tag}"
    s.data.pop(K_DRAFT, None)
    await show_preview(update, s)


async def step_btn_name(update: Update, s: Session) -> None:
    name = (update.effective_message.text or "").strip()
    if not name:
        await reply(update, T.ASK_BTN_NAME)
        return
    if len(name) > MAX_BUTTON_TEXT:
        await reply(update, T.ERR_TOO_LONG.format(limit=MAX_BUTTON_TEXT))
        return
    s.draft["name"] = name
    s.state = State.BTN_LINK
    await reply(update, T.ASK_BTN_LINK, kb_cancel())


async def step_btn_link(update: Update, s: Session) -> None:
    url = normalize_url(update.effective_message.text or "")
    if not url:
        await reply(update, T.ERR_NOT_LINK)
        return
    s.draft["url"] = url
    s.state = State.BTN_COLOR
    await reply(update, T.ASK_BTN_COLOR, kb_colors())


async def step_btn_color(update: Update, s: Session) -> None:
    color = COLOR_BY_LABEL.get((update.effective_message.text or "").strip())
    if not color:
        await reply(update, T.ERR_PICK, kb_colors())
        return
    draft = s.draft
    if not draft.get("name") or not draft.get("url"):
        return await ask_button(update, s)
    s.snapshot()
    s.post.buttons.append(Button(draft["name"], draft["url"], color))
    if await show_preview(update, s):
        s.data.pop(K_DRAFT, None)
        return
    s.post.buttons.pop()
    s.history.pop()
    draft.pop("url", None)
    s.state = State.BTN_LINK
    await reply(update, T.ERR_LINK_REJECTED, kb_cancel())


STEPS = {
    State.MEDIA: step_media,
    State.MENU: step_menu,
    State.TEXT: step_text,
    State.STYLE: step_style,
    State.BTN_NAME: step_btn_name,
    State.BTN_LINK: step_btn_link,
    State.BTN_COLOR: step_btn_color,
}


# ---------------------------------------------------------------- router
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = Session(context)
    text = (update.effective_message.text or "").strip()

    if text == T.BTN_NEW:
        return await cmd_new(update, context)
    if text == T.BTN_HELP:
        return await cmd_help(update, context)
    if text == T.BTN_CANCEL:
        return await cmd_cancel(update, context)

    handler = STEPS.get(s.state)
    if handler is None:
        await reply(update, T.IDLE.format(new=T.BTN_NEW), kb_main())
        return
    await handler(update, s)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, (NetworkError, TimedOut, RetryAfter)):
        logger.warning("Transient Telegram error: %s", err)
        return
    if isinstance(err, Forbidden):
        logger.info("Bot blocked by user: %s", err)
        return
    logger.error("Unhandled error", exc_info=err)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(T.ERR_GENERIC, reply_markup=kb_main())
        except TelegramError:
            pass


def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", cmd_start, private))
    app.add_handler(CommandHandler("help", cmd_help, private))
    app.add_handler(CommandHandler("new", cmd_new, private))
    app.add_handler(CommandHandler("cancel", cmd_cancel, private))
    app.add_handler(MessageHandler(private & ~filters.COMMAND & ~filters.StatusUpdate.ALL, on_message))
    app.add_error_handler(on_error)
