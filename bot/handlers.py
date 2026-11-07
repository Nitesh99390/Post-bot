"""Bot side of Post Maker: almost no chat text, everything lives in the Mini App.

The bot only (1) shows one button that opens the Mini App and (2) keeps the
list of groups and channels up to date when it is added, promoted or removed.
"""

from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config
from .chats import CHAT_TYPES, chat_type, register_chat
from .store import MemoryStore, StoreError

logger = logging.getLogger(__name__)

COMMANDS = (("start", "Open Post Maker"),)


def get_store(context: ContextTypes.DEFAULT_TYPE):
    store = context.bot_data.get("store")
    if store is None:
        store = context.bot_data["store"] = MemoryStore()
    return store


def open_markup() -> InlineKeyboardMarkup | None:
    url = config.webapp_url()
    if not url:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open Post Maker", web_app=WebAppInfo(url), style="primary")]]
    )


def menu_button() -> MenuButtonWebApp | None:
    url = config.webapp_url()
    return MenuButtonWebApp(text="Post Maker", web_app=WebAppInfo(url)) if url else None


async def first_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Once per user and process: drop old keyboards and menu overrides."""
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat:
        return
    seen: set[int] = context.bot_data.setdefault("seen_users", set())
    if user.id in seen:
        return
    seen.add(user.id)
    try:  # the previous bot version left a "Create Post" keyboard behind
        gone = await context.bot.send_message(
            chat.id, "\u2060", reply_markup=ReplyKeyboardRemove(), disable_notification=True
        )
        await context.bot.delete_message(chat.id, gone.message_id)
    except TelegramError:
        pass
    button = menu_button()
    if button:
        try:
            await context.bot.set_chat_menu_button(chat_id=chat.id, menu_button=button)
        except TelegramError as error:
            logger.info("Menu button skipped (%s)", type(error).__name__)


async def on_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any private message gets the same one-line answer with the app button."""
    await first_contact(update, context)
    markup = open_markup()
    if markup:
        await update.effective_message.reply_text("Tap below to open the app.", reply_markup=markup)
    else:
        await update.effective_message.reply_text("The Mini App is not configured yet.")


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Link a group or channel the moment the bot is added there by an admin."""
    change = update.my_chat_member
    if not change or chat_type(change.chat) not in CHAT_TYPES:
        return
    store, new = get_store(context), change.new_chat_member
    try:
        if new.status in ("left", "kicked"):
            await store.drop_chat(change.chat.id)
            return
        if new.status not in ("administrator", "member", "restricted", "creator"):
            return
        await register_chat(
            context.bot, store, change.from_user.id, change.chat, new
        )
    except (StoreError, TelegramError) as error:
        logger.warning("Chat link failed (%s)", type(error).__name__)


async def on_migrate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message and message.migrate_to_chat_id:
        try:
            await get_store(context).migrate_chat(message.chat.id, message.migrate_to_chat_id)
        except StoreError as error:
            logger.warning("Chat migration failed (%s)", error)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update failed (%s)", type(context.error).__name__)


def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler(["start", "help", "app"], on_private, private))
    app.add_handler(MessageHandler(private & ~filters.StatusUpdate.ALL, on_private))
    app.add_handler(MessageHandler(filters.StatusUpdate.MIGRATE, on_migrate))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_error_handler(on_error)
