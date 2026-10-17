"""All Telegram handlers for the Post Bot."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import storage
from .config import ADMIN_IDS, TZ
from .post import Post, extract_media, message_html, parse_buttons

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo(TZ)

# user_data keys
K_POST = "post"
K_STATE = "state"
K_TARGETS = "targets"

# states
S_IDLE = None
S_WAIT_CONTENT = "wait_content"
S_WAIT_BUTTONS = "wait_buttons"
S_WAIT_ADD_CHANNEL = "wait_add_channel"
S_WAIT_SCHEDULE = "wait_schedule"


# ====================================================================== auth
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
        user = update.effective_user
        if ADMIN_IDS and (user is None or user.id not in ADMIN_IDS):
            if update.callback_query:
                await update.callback_query.answer("⛔ You are not authorized.", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("⛔ You are not authorized to use this bot.")
            return
        return await func(update, context, *a, **kw)

    return wrapper


# ====================================================================== helpers
def get_post(context: ContextTypes.DEFAULT_TYPE) -> Post:
    post = context.user_data.get(K_POST)
    if post is None:
        post = Post()
        context.user_data[K_POST] = post
    return post


def reset_post(context: ContextTypes.DEFAULT_TYPE) -> Post:
    context.user_data[K_POST] = Post()
    context.user_data[K_STATE] = S_IDLE
    context.user_data[K_TARGETS] = set()
    return context.user_data[K_POST]


def onoff(v: bool) -> str:
    return "✅" if v else "☐"


def editor_keyboard(post: Post) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📝 Content", callback_data="ed:content"),
            InlineKeyboardButton("🔘 Buttons", callback_data="ed:buttons"),
        ],
        [
            InlineKeyboardButton(f"{onoff(post.disable_preview)} No link preview", callback_data="ed:toggle:disable_preview"),
            InlineKeyboardButton(f"{onoff(post.silent)} Silent", callback_data="ed:toggle:silent"),
        ],
        [
            InlineKeyboardButton(f"{onoff(post.protect_content)} Protect", callback_data="ed:toggle:protect_content"),
            InlineKeyboardButton(f"{onoff(post.pin)} Pin", callback_data="ed:toggle:pin"),
        ],
        [
            InlineKeyboardButton("👁 Preview", callback_data="ed:preview"),
            InlineKeyboardButton("🗑 Clear", callback_data="ed:clear"),
        ],
        [
            InlineKeyboardButton("📤 Send Now", callback_data="ed:send"),
            InlineKeyboardButton("⏰ Schedule", callback_data="ed:schedule"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def editor_summary(post: Post) -> str:
    media = post.media_type or "none"
    text_len = len(post.text)
    btn_count = sum(len(r) for r in post.buttons)
    lines = [
        "<b>📋 Post Editor</b>",
        "",
        f"• Media: <code>{media}</code>",
        f"• Text: <code>{text_len} chars</code>",
        f"• Buttons: <code>{btn_count}</code> in <code>{len(post.buttons)}</code> row(s)",
        "",
        "Send me a message (text / photo / video / GIF / document) to set the content, "
        "or use the buttons below.",
    ]
    return "\n".join(lines)


async def show_editor(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    post = get_post(context)
    context.user_data[K_STATE] = S_IDLE
    text = editor_summary(post)
    kb = editor_keyboard(post)
    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
            return
        except TelegramError:
            pass
    await update.effective_message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


def targets_keyboard(user_id: int, selected: set[str], action: str) -> InlineKeyboardMarkup:
    channels = storage.get_channels(user_id)
    rows = []
    for cid, info in channels.items():
        mark = "✅" if cid in selected else "☐"
        rows.append([InlineKeyboardButton(f"{mark} {info['title']}", callback_data=f"tg:{action}:{cid}")])
    rows.append(
        [
            InlineKeyboardButton("☑️ All", callback_data=f"tg:{action}:all"),
            InlineKeyboardButton("🚀 Confirm", callback_data=f"tg:{action}:go"),
        ]
    )
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="ed:back")])
    return InlineKeyboardMarkup(rows)


# ====================================================================== commands
@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Hi <b>{user.first_name}</b>!\n\n"
        "I'm a <b>Post Bot</b>. I help you create rich posts with media, formatted text and "
        "inline URL buttons, then publish them to your channels/groups instantly or on schedule.\n\n"
        "<b>Commands</b>\n"
        "/newpost – start creating a post\n"
        "/channels – manage your channels\n"
        "/addchannel – add a channel (forward a message or send @username)\n"
        "/scheduled – view scheduled posts\n"
        "/myid – show your Telegram user ID\n"
        "/help – detailed help\n\n"
        "💡 <i>Tip: add me as admin in your channel with 'Post Messages' permission first.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>📖 How to use</b>\n\n"
        "<b>1. Add a channel</b>\n"
        "Make the bot admin in your channel, then /addchannel and forward any message "
        "from the channel (or send <code>@channelusername</code> / chat ID).\n\n"
        "<b>2. Create a post</b>\n"
        "/newpost → send text, photo, video, GIF or document with caption. "
        "Formatting (bold, italic, links, spoilers…) is preserved.\n\n"
        "<b>3. Add buttons</b>\n"
        "Tap 🔘 Buttons and send in this format (one row per line, <code>|</code> for same row):\n"
        "<code>Join Channel - https://t.me/example\n"
        "Website - https://example.com | Contact - https://t.me/user</code>\n\n"
        "<b>4. Options</b>\n"
        "• No link preview – hide web preview\n"
        "• Silent – send without notification\n"
        "• Protect – disable forwarding/saving\n"
        "• Pin – pin after posting\n\n"
        "<b>5. Publish</b>\n"
        "👁 Preview → 📤 Send Now or ⏰ Schedule.\n"
        f"Schedule formats (timezone <code>{TZ}</code>):\n"
        "<code>2025-12-31 18:30</code>, <code>18:30</code> (today/tomorrow), "
        "<code>+30m</code>, <code>+2h</code>, <code>+1d</code>\n\n"
        "<b>Other</b>\n"
        "/cancel – abort current action\n"
        "/channels – list/remove channels\n"
        "/scheduled – list/cancel scheduled posts"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@admin_only
async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Your user ID: <code>{update.effective_user.id}</code>\n"
        f"Chat ID: <code>{update.effective_chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[K_STATE] = S_IDLE
    await update.message.reply_text("❎ Cancelled. Use /newpost to start again.")


@admin_only
async def cmd_newpost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_post(context)
    context.user_data[K_STATE] = S_WAIT_CONTENT
    await update.message.reply_text(
        "✍️ Send me the post content now.\n\n"
        "It can be text, a photo, video, GIF, or document (with optional caption). "
        "Formatting is preserved.\n\nUse /cancel to abort.",
    )


# ---------------------------------------------------------------- channels
@admin_only
async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[K_STATE] = S_WAIT_ADD_CHANNEL
    await update.message.reply_text(
        "➕ <b>Add a channel/group</b>\n\n"
        "1. Make me an admin there with <i>Post Messages</i> permission.\n"
        "2. Forward any message from it here, or send its <code>@username</code> or chat ID "
        "(e.g. <code>-1001234567890</code>).\n\n/cancel to abort.",
        parse_mode=ParseMode.HTML,
    )


async def _register_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, ref: int | str):
    user_id = update.effective_user.id
    try:
        chat = await context.bot.get_chat(ref)
        me = await context.bot.get_chat_member(chat.id, context.bot.id)
        status = me.status
        can_post = status == "creator" or (
            status == "administrator"
            and (chat.type != ChatType.CHANNEL or getattr(me, "can_post_messages", False))
        )
        if not can_post:
            await update.message.reply_text(
                f"⚠️ I'm not an admin with posting rights in <b>{chat.title}</b>. "
                "Please promote me and try again.",
                parse_mode=ParseMode.HTML,
            )
            return
        storage.add_channel(user_id, chat.id, chat.title or str(chat.id), chat.username)
        context.user_data[K_STATE] = S_IDLE
        await update.message.reply_text(
            f"✅ Added <b>{chat.title}</b> (<code>{chat.id}</code>).\nUse /channels to manage.",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as e:
        await update.message.reply_text(
            f"❌ Could not access that chat: <code>{e.message}</code>\n"
            "Make sure I'm added as admin there.",
            parse_mode=ParseMode.HTML,
        )


def channels_keyboard(user_id: int) -> InlineKeyboardMarkup | None:
    channels = storage.get_channels(user_id)
    if not channels:
        return None
    rows = [
        [InlineKeyboardButton(f"🗑 {info['title']}", callback_data=f"ch:rm:{cid}")]
        for cid, info in channels.items()
    ]
    return InlineKeyboardMarkup(rows)


@admin_only
async def cmd_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    channels = storage.get_channels(user_id)
    if not channels:
        await update.message.reply_text("📭 No channels yet. Use /addchannel to add one.")
        return
    lines = ["<b>📢 Your channels</b> (tap to remove)\n"]
    for cid, info in channels.items():
        uname = f" @{info['username']}" if info.get("username") else ""
        lines.append(f"• {info['title']}{uname} — <code>{cid}</code>")
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=channels_keyboard(user_id)
    )


@admin_only
async def cb_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, action, cid = q.data.split(":", 2)
    user_id = q.from_user.id
    if action == "rm":
        storage.remove_channel(user_id, cid)
        await q.answer("Removed")
        channels = storage.get_channels(user_id)
        if not channels:
            await q.edit_message_text("📭 No channels left. Use /addchannel to add one.")
            return
        lines = ["<b>📢 Your channels</b> (tap to remove)\n"]
        for c, info in channels.items():
            lines.append(f"• {info['title']} — <code>{c}</code>")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=channels_keyboard(user_id)
        )


# ---------------------------------------------------------------- scheduled
@admin_only
async def cmd_scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = storage.get_scheduled(update.effective_user.id)
    if not items:
        await update.message.reply_text("📭 No scheduled posts.")
        return
    lines = ["<b>⏰ Scheduled posts</b> (tap to cancel)\n"]
    rows = []
    for it in sorted(items, key=lambda x: x["when"]):
        when = datetime.fromisoformat(it["when"]).astimezone(LOCAL_TZ).strftime("%d %b %Y %H:%M")
        preview = (it["post"].get("text") or it["post"].get("media_type") or "")[:40].replace("\n", " ")
        lines.append(f"• <code>{when}</code> → {len(it['chat_ids'])} chat(s): <i>{preview}</i>")
        rows.append([InlineKeyboardButton(f"🗑 {when}", callback_data=f"sc:rm:{it['id']}")])
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows)
    )


@admin_only
async def cb_scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, action, job_id = q.data.split(":", 2)
    if action == "rm":
        storage.remove_scheduled(job_id)
        for job in context.job_queue.get_jobs_by_name(job_id):
            job.schedule_removal()
        await q.answer("Cancelled")
        await q.edit_message_text("🗑 Scheduled post cancelled. Use /scheduled to view others.")


# ====================================================================== message router
@admin_only
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    state = context.user_data.get(K_STATE)

    # ---- adding channel
    if state == S_WAIT_ADD_CHANNEL:
        origin = msg.forward_origin
        if origin is not None and getattr(origin, "chat", None) is not None:
            await _register_channel(update, context, origin.chat.id)
            return
        text = (msg.text or "").strip()
        if text.startswith("@") or text.lstrip("-").isdigit():
            ref: int | str = int(text) if text.lstrip("-").isdigit() else text
            await _register_channel(update, context, ref)
            return
        await msg.reply_text("Please forward a message from the channel or send @username / chat ID.")
        return

    # ---- buttons
    if state == S_WAIT_BUTTONS:
        post = get_post(context)
        raw = msg.text or ""
        if raw.strip().lower() in {"none", "clear", "remove"}:
            post.buttons = []
            await msg.reply_text("🔘 Buttons removed.")
        else:
            try:
                post.buttons = parse_buttons(raw)
                await msg.reply_text(f"✅ {sum(len(r) for r in post.buttons)} button(s) set.")
            except ValueError as e:
                await msg.reply_text(
                    f"❌ {e}\n\nFormat:\n<code>Text - https://url</code>\n"
                    "Use <code>|</code> to put buttons on the same row, new line for new row.",
                    parse_mode=ParseMode.HTML,
                )
                return
        await show_editor(update, context)
        return

    # ---- schedule time
    if state == S_WAIT_SCHEDULE:
        when = parse_schedule(msg.text or "")
        if when is None:
            await msg.reply_text(
                "❌ Couldn't parse that time. Try:\n"
                "<code>2025-12-31 18:30</code>, <code>18:30</code>, <code>+30m</code>, <code>+2h</code>, <code>+1d</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        await schedule_post(update, context, when)
        return

    # ---- content (default: any message sets content when a post exists or waiting)
    if state == S_WAIT_CONTENT or K_POST in context.user_data:
        post = get_post(context)
        media_type, file_id = extract_media(msg)
        post.media_type, post.file_id = media_type, file_id
        post.text = message_html(msg)
        if post.is_empty():
            await msg.reply_text("⚠️ Unsupported content. Send text, photo, video, GIF, document or audio.")
            return
        # Carry over inline buttons if the user forwarded a message with them
        if msg.reply_markup and msg.reply_markup.inline_keyboard and not post.buttons:
            rows = []
            for r in msg.reply_markup.inline_keyboard:
                row = [{"text": b.text, "url": b.url} for b in r if b.url]
                if row:
                    rows.append(row)
            post.buttons = rows
        await show_editor(update, context)
        return

    await msg.reply_text("Use /newpost to create a post, or /help for instructions.")


# ====================================================================== editor callbacks
@admin_only
async def cb_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split(":")
    action = parts[1]
    post = get_post(context)
    user_id = q.from_user.id

    if action == "content":
        context.user_data[K_STATE] = S_WAIT_CONTENT
        await q.answer()
        await q.message.reply_text("✍️ Send the new content (text / media with caption).")

    elif action == "buttons":
        context.user_data[K_STATE] = S_WAIT_BUTTONS
        await q.answer()
        current = ""
        if post.buttons:
            current = "\n\nCurrent:\n<code>" + "\n".join(
                " | ".join(f"{b['text']} - {b['url']}" for b in row) for row in post.buttons
            ) + "</code>"
        await q.message.reply_text(
            "🔘 Send buttons in this format (one row per line, <code>|</code> separates buttons in a row):\n\n"
            "<code>Join - https://t.me/example\nSite - https://example.com | Contact - https://t.me/user</code>\n\n"
            "Send <code>none</code> to remove all buttons." + current,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    elif action == "toggle":
        attr = parts[2]
        setattr(post, attr, not getattr(post, attr))
        await q.answer()
        await show_editor(update, context, edit=True)

    elif action == "preview":
        if post.is_empty():
            await q.answer("Post is empty! Send some content first.", show_alert=True)
            return
        await q.answer()
        try:
            await post.send(context.bot, q.message.chat_id) if not post.pin else await _send_nopin(post, context, q.message.chat_id)
        except TelegramError as e:
            await q.message.reply_text(f"❌ Preview failed: <code>{e.message}</code>", parse_mode=ParseMode.HTML)
            return
        await show_editor(update, context)

    elif action == "clear":
        reset_post(context)
        context.user_data[K_STATE] = S_WAIT_CONTENT
        await q.answer("Cleared")
        await q.edit_message_text("🗑 Post cleared. Send new content.")

    elif action in ("send", "schedule"):
        if post.is_empty():
            await q.answer("Post is empty!", show_alert=True)
            return
        channels = storage.get_channels(user_id)
        if not channels:
            await q.answer()
            await q.message.reply_text("📭 No channels. Use /addchannel first.")
            return
        await q.answer()
        selected = context.user_data.setdefault(K_TARGETS, set())
        if len(channels) == 1:
            selected.update(channels.keys())
        label = "📤 Send now" if action == "send" else "⏰ Schedule"
        await q.edit_message_text(
            f"<b>{label}</b>\n\nSelect target channel(s):",
            parse_mode=ParseMode.HTML,
            reply_markup=targets_keyboard(user_id, selected, action),
        )

    elif action == "back":
        await q.answer()
        await show_editor(update, context, edit=True)


async def _send_nopin(post: Post, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Preview shouldn't pin in the private chat."""
    saved = post.pin
    post.pin = False
    try:
        await post.send(context.bot, chat_id)
    finally:
        post.pin = saved


@admin_only
async def cb_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, action, cid = q.data.split(":", 2)
    user_id = q.from_user.id
    selected: set[str] = context.user_data.setdefault(K_TARGETS, set())
    channels = storage.get_channels(user_id)

    if cid == "all":
        if len(selected) == len(channels):
            selected.clear()
        else:
            selected.update(channels.keys())
        await q.answer()
        await q.edit_message_reply_markup(targets_keyboard(user_id, selected, action))
        return

    if cid == "go":
        if not selected:
            await q.answer("Select at least one channel.", show_alert=True)
            return
        await q.answer()
        if action == "send":
            await publish_now(update, context)
        else:
            context.user_data[K_STATE] = S_WAIT_SCHEDULE
            now = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
            await q.edit_message_text(
                f"⏰ When should I post? (timezone <code>{TZ}</code>, now: <code>{now}</code>)\n\n"
                "Examples: <code>2025-12-31 18:30</code>, <code>18:30</code>, <code>+30m</code>, "
                "<code>+2h</code>, <code>+1d</code>\n\n/cancel to abort.",
                parse_mode=ParseMode.HTML,
            )
        return

    # toggle single
    if cid in selected:
        selected.discard(cid)
    else:
        selected.add(cid)
    await q.answer()
    await q.edit_message_reply_markup(targets_keyboard(user_id, selected, action))


# ====================================================================== publishing
async def _deliver(bot, post: Post, chat_ids: list[int]) -> tuple[list[str], list[str]]:
    ok, failed = [], []
    for cid in chat_ids:
        try:
            msg = await post.send(bot, cid)
            link = ""
            if msg.chat.username:
                link = f" — https://t.me/{msg.chat.username}/{msg.message_id}"
            ok.append(f"{msg.chat.title or cid}{link}")
        except TelegramError as e:
            failed.append(f"{cid}: {e.message}")
            logger.warning("Failed to post to %s: %s", cid, e)
    return ok, failed


@admin_only
async def publish_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    post = get_post(context)
    chat_ids = [int(c) for c in context.user_data.get(K_TARGETS, set())]
    await q.edit_message_text("⏳ Sending…")
    ok, failed = await _deliver(context.bot, post, chat_ids)
    text = "<b>📤 Result</b>\n\n"
    if ok:
        text += "✅ Sent to:\n" + "\n".join(f"• {x}" for x in ok) + "\n"
    if failed:
        text += "\n❌ Failed:\n" + "\n".join(f"• <code>{x}</code>" for x in failed)
    await q.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    reset_post(context)


def parse_schedule(raw: str) -> datetime | None:
    raw = raw.strip().lower()
    now = datetime.now(LOCAL_TZ)
    if not raw:
        return None
    if raw.startswith("+"):
        unit = raw[-1]
        try:
            n = int(raw[1:-1])
        except ValueError:
            return None
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}.get(unit)
        return now + delta if delta else None
    for fmt in ("%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    for fmt in ("%H:%M", "%H.%M"):
        try:
            t = datetime.strptime(raw, fmt).time()
            dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if dt <= now:
                dt += timedelta(days=1)
            return dt
        except ValueError:
            continue
    return None


async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE, when: datetime):
    now = datetime.now(LOCAL_TZ)
    if when <= now:
        await update.message.reply_text("❌ That time is in the past. Try again.")
        return
    post = get_post(context)
    chat_ids = [int(c) for c in context.user_data.get(K_TARGETS, set())]
    job_id = uuid.uuid4().hex[:10]
    item = {
        "id": job_id,
        "user_id": update.effective_user.id,
        "chat_ids": chat_ids,
        "when": when.isoformat(),
        "post": post.to_dict(),
    }
    storage.add_scheduled(item)
    context.job_queue.run_once(run_scheduled_job, when=when, name=job_id, data=item)
    await update.message.reply_text(
        f"✅ Scheduled for <code>{when.strftime('%d %b %Y %H:%M')}</code> ({TZ}) "
        f"to {len(chat_ids)} chat(s).\nUse /scheduled to manage.",
        parse_mode=ParseMode.HTML,
    )
    reset_post(context)


async def run_scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    item = context.job.data
    post = Post.from_dict(item["post"])
    ok, failed = await _deliver(context.bot, post, item["chat_ids"])
    storage.remove_scheduled(item["id"])
    text = "<b>⏰ Scheduled post delivered</b>\n\n"
    if ok:
        text += "✅ " + "\n✅ ".join(ok) + "\n"
    if failed:
        text += "\n❌ " + "\n❌ ".join(f"<code>{x}</code>" for x in failed)
    try:
        await context.bot.send_message(item["user_id"], text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except TelegramError:
        pass


def restore_scheduled_jobs(app: Application) -> int:
    """Re-register scheduled jobs after a restart."""
    count = 0
    now = datetime.now(LOCAL_TZ)
    for item in storage.get_scheduled():
        when = datetime.fromisoformat(item["when"])
        if when <= now:
            when = now + timedelta(seconds=5)  # missed while offline → send ASAP
        app.job_queue.run_once(run_scheduled_job, when=when, name=item["id"], data=item)
        count += 1
    return count


# ====================================================================== error handler
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Something went wrong. Please try again.")
        except TelegramError:
            pass


# ====================================================================== registration
def register(app: Application) -> None:
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", cmd_start, private))
    app.add_handler(CommandHandler("help", cmd_help, private))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("cancel", cmd_cancel, private))
    app.add_handler(CommandHandler("newpost", cmd_newpost, private))
    app.add_handler(CommandHandler(["addchannel", "add"], cmd_addchannel, private))
    app.add_handler(CommandHandler("channels", cmd_channels, private))
    app.add_handler(CommandHandler("scheduled", cmd_scheduled, private))

    app.add_handler(CallbackQueryHandler(cb_editor, pattern=r"^ed:"))
    app.add_handler(CallbackQueryHandler(cb_targets, pattern=r"^tg:"))
    app.add_handler(CallbackQueryHandler(cb_channels, pattern=r"^ch:"))
    app.add_handler(CallbackQueryHandler(cb_scheduled, pattern=r"^sc:"))

    app.add_handler(MessageHandler(private & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
