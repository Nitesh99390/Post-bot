"""Telegram bot — inline-keyboard driven post builder (state machine, single draft card)."""
import html
import logging
import re
import time

import telebot
from telebot.types import (InlineKeyboardMarkup as Markup, InlineKeyboardButton as Btn,
                           WebAppInfo, MenuButtonWebApp, BotCommand)

import db
from config import BOT_TOKEN, APP_LINK, DEFAULT_CHANNEL, MAX_BUTTONS, SESSION_TTL

log = logging.getLogger("bot")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# chat_id -> draft dict {state, text, photo, buttons, card_id, pending_name, saved, ts}
drafts: dict[int, dict] = {}
URL_RE = re.compile(r"^(https?://|tg://)[^\s]+$", re.I)


# ───────────────────────── helpers ─────────────────────────
def draft(chat_id: int) -> dict | None:
    d = drafts.get(chat_id)
    if d and time.time() - d["ts"] > SESSION_TTL:
        drafts.pop(chat_id, None)
        return None
    if d:
        d["ts"] = time.time()
    return d


def new_draft(chat_id: int, **kw) -> dict:
    d = {"state": "text", "text": "", "photo": None, "buttons": [], "card_id": None,
         "pending_name": None, "saved": False, "ts": time.time()}
    d.update(kw)
    drafts[chat_id] = d
    return d


def normalize_url(raw: str) -> str | None:
    u = raw.strip()
    if u.startswith("@"):
        u = f"https://t.me/{u[1:]}"
    elif not re.match(r"^(https?|tg)://", u, re.I):
        u = "https://" + u
    return u if URL_RE.match(u) and ("." in u or u.startswith("tg://")) else None


def parse_bulk(text: str) -> list:
    """`Name | URL` per line — ek saath multiple buttons add karne ke liye."""
    out = []
    for line in text.splitlines():
        if "|" in line:
            name, url = line.split("|", 1)
            u = normalize_url(url)
            if name.strip() and u:
                out.append({"name": name.strip()[:64], "url": u})
    return out


def post_markup(buttons: list) -> Markup | None:
    if not buttons:
        return None
    m = Markup()
    for b in buttons:
        m.add(Btn(b["name"], url=b["url"]))
    return m


def send_post(chat, d: dict):
    """Draft ko kisi bhi chat me deliver karo (photo ya text)."""
    if d["photo"]:
        return bot.send_photo(chat, d["photo"], caption=d["text"], reply_markup=post_markup(d["buttons"]))
    return bot.send_message(chat, d["text"], reply_markup=post_markup(d["buttons"]),
                            disable_web_page_preview=True)


def cancel_kb() -> Markup:
    return Markup().add(Btn("❌ Cancel", callback_data="cancel"))


def home_kb() -> Markup:
    m = Markup(row_width=2)
    m.add(Btn("✨ New Post", callback_data="new"),
          Btn("📊 Dashboard", web_app=WebAppInfo(url=f"{APP_LINK}/app")))
    m.add(Btn("🗂 My Posts", callback_data="myposts"), Btn("ℹ️ Help", callback_data="help"))
    return m


def card_kb(d: dict) -> Markup:
    m = Markup(row_width=2)
    m.add(Btn("➕ Add Button", callback_data="addbtn"), Btn("✏️ Edit Text", callback_data="edittext"))
    if d["buttons"]:
        m.add(Btn("↩️ Remove Last", callback_data="rmbtn"), Btn("🧹 Clear Buttons", callback_data="clearbtn"))
    m.add(Btn("👁 Preview", callback_data="preview"), Btn("🚀 Publish", callback_data="publish"))
    m.add(Btn("❌ Discard", callback_data="cancel"))
    return m


def card_text(d: dict) -> str:
    preview = html.escape(re.sub(r"<[^>]+>", "", d["text"]))[:300]
    lines = [f"📝 <b>Post Draft</b>{' · 🖼 photo' if d['photo'] else ''}", "",
             f"<blockquote>{preview}{'…' if len(d['text']) > 300 else ''}</blockquote>", "",
             f"🔘 <b>Buttons ({len(d['buttons'])}/{MAX_BUTTONS})</b>"]
    lines += [f"  {i}. {html.escape(b['name'])}" for i, b in enumerate(d["buttons"], 1)] or ["  <i>none yet</i>"]
    return "\n".join(lines)


def show_card(chat_id: int, d: dict):
    """Ek hi draft card ko edit karte raho — chat clean rehta hai."""
    d["state"] = "idle"
    try:
        if d["card_id"]:
            bot.edit_message_text(card_text(d), chat_id, d["card_id"], reply_markup=card_kb(d))
            return
    except Exception:
        pass
    d["card_id"] = bot.send_message(chat_id, card_text(d), reply_markup=card_kb(d)).message_id


def ask(chat_id: int, d: dict, state: str, text: str):
    d["state"] = state
    bot.send_message(chat_id, text, reply_markup=cancel_kb())


# ───────────────────────── commands ─────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(m):
    try:
        bot.set_chat_menu_button(m.chat.id, MenuButtonWebApp(
            "web_app", "📊 Dashboard", WebAppInfo(url=f"{APP_LINK}/app")))
    except Exception:
        pass
    bot.send_message(m.chat.id,
                     f"👋 Hi <b>{html.escape(m.from_user.first_name)}</b>!\n\n"
                     "I create beautiful channel posts with inline URL buttons.\n"
                     "Text, photos, formatting — sab supported.", reply_markup=home_kb())


@bot.message_handler(commands=["cancel"])
def cmd_cancel(m):
    drafts.pop(m.chat.id, None)
    bot.send_message(m.chat.id, "✅ Cancelled.", reply_markup=home_kb())


@bot.message_handler(commands=["new"])
def cmd_new(m):
    start_new(m.chat.id)


@bot.message_handler(commands=["myposts"])
def cmd_myposts(m):
    show_my_posts(m.chat.id, m.from_user.id)


@bot.message_handler(commands=["help"])
def cmd_help(m):
    bot.send_message(m.chat.id, HELP, reply_markup=home_kb())


HELP = (
    "ℹ️ <b>How it works</b>\n\n"
    "1️⃣ Send post text (or a photo with caption). Telegram formatting is preserved.\n"
    "2️⃣ Add buttons — one by one, or bulk:\n"
    "<code>Join | @mychannel\nWebsite | example.com</code>\n"
    "3️⃣ Preview → Publish to the channel or any chat where I'm admin.\n\n"
    "<b>Commands:</b> /new · /myposts · /cancel"
)


def start_new(chat_id: int):
    d = new_draft(chat_id)
    ask(chat_id, d, "text", "✍️ Send the <b>post text</b> or a <b>photo with caption</b>.\n"
        "<i>Use Telegram formatting or raw HTML tags.</i>")


def show_my_posts(chat_id: int, user_id: int):
    posts = db.get_user_posts(user_id)
    if not posts:
        bot.send_message(chat_id, "🗂 You haven't published anything yet.", reply_markup=home_kb())
        return
    m = Markup(row_width=1)
    for p in posts:
        title = re.sub(r"<[^>]+>", "", p["message_text"]).strip().split("\n")[0][:40] or "Untitled"
        m.add(Btn(f"♻️ {title}", callback_data=f"reuse:{p['id']}"))
    bot.send_message(chat_id, "🗂 <b>Your recent posts</b> — tap to reuse as a new draft:", reply_markup=m)


# ───────────────────────── callbacks ─────────────────────────
@bot.callback_query_handler(func=lambda c: True)
def on_callback(c):
    chat_id, data = c.message.chat.id, c.data
    bot.answer_callback_query(c.id)
    d = draft(chat_id)

    if data == "new":
        return start_new(chat_id)
    if data == "help":
        return bot.send_message(chat_id, HELP, reply_markup=home_kb())
    if data == "myposts":
        return show_my_posts(chat_id, c.from_user.id)
    if data == "cancel":
        drafts.pop(chat_id, None)
        try:
            bot.edit_message_text("🗑 Draft discarded.", chat_id, c.message.message_id)
        except Exception:
            pass
        return bot.send_message(chat_id, "What next?", reply_markup=home_kb())
    if data.startswith("reuse:"):
        post = next((p for p in db.get_user_posts(c.from_user.id, 50) if str(p["id"]) == data[6:]), None)
        if not post:
            return bot.send_message(chat_id, "⚠️ Post not found.")
        d = new_draft(chat_id, text=post["message_text"], buttons=db.parse_buttons(post))
        return show_card(chat_id, d)

    if not d:
        return bot.send_message(chat_id, "⌛ Session expired. Start a new post.", reply_markup=home_kb())

    if data == "addbtn":
        if len(d["buttons"]) >= MAX_BUTTONS:
            return bot.answer_callback_query(c.id, f"Max {MAX_BUTTONS} buttons!", show_alert=True)
        ask(chat_id, d, "btn_name", f"🔘 Send <b>button {len(d['buttons']) + 1} text</b>\n"
            "<i>or bulk add:</i> <code>Name | URL</code> (one per line)")
    elif data == "edittext":
        ask(chat_id, d, "text", "✍️ Send the new <b>post text</b> (or photo with caption):")
    elif data == "rmbtn":
        d["buttons"] and d["buttons"].pop()
        show_card(chat_id, d)
    elif data == "clearbtn":
        d["buttons"].clear()
        show_card(chat_id, d)
    elif data == "preview":
        try:
            send_post(chat_id, d)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Telegram rejected the post:\n<code>{html.escape(str(e))}</code>\n"
                             "Check your HTML tags.")
        d["card_id"] = None
        show_card(chat_id, d)
    elif data == "publish":
        m = Markup(row_width=1)
        m.add(Btn(f"📢 {DEFAULT_CHANNEL}", callback_data="pub:default"),
              Btn("💬 Other channel / group", callback_data="pub:custom"),
              Btn("⬅️ Back", callback_data="back"))
        d["state"] = "idle"
        bot.edit_message_text("🚀 <b>Where should I publish?</b>", chat_id, c.message.message_id, reply_markup=m)
    elif data == "back":
        d["card_id"] = c.message.message_id
        show_card(chat_id, d)
    elif data == "pub:default":
        publish(chat_id, d, DEFAULT_CHANNEL, c.from_user)
    elif data == "pub:custom":
        ask(chat_id, d, "target", "💬 Send the target <b>@username</b> or <b>chat ID</b>:")


def publish(chat_id: int, d: dict, target, user):
    try:
        sent = send_post(target, d)
    except Exception as e:
        bot.send_message(chat_id, f"❌ <b>Failed to publish to</b> <code>{html.escape(str(target))}</code>\n"
                         f"<i>{html.escape(str(e))}</i>\n\nMake sure I'm an admin there.")
        return show_card(chat_id, d)

    if not d["saved"]:
        db.save_post(user.id, user.username or user.first_name, d["text"], d["buttons"])
        d["saved"] = True

    link = ""
    if getattr(sent.chat, "username", None):
        link = f"\n🔗 https://t.me/{sent.chat.username}/{sent.message_id}"
    m = Markup(row_width=2)
    m.add(Btn("🔁 Publish elsewhere", callback_data="publish"), Btn("✨ New Post", callback_data="new"))
    d["card_id"] = None
    bot.send_message(chat_id, f"✅ <b>Published to</b> {html.escape(sent.chat.title or str(target))}{link}",
                     reply_markup=m, disable_web_page_preview=True)


# ───────────────────────── state-driven messages ─────────────────────────
@bot.message_handler(content_types=["text", "photo"])
def on_message(m):
    chat_id = m.chat.id
    d = draft(chat_id)
    if not d or d["state"] == "idle":
        return bot.send_message(chat_id, "Use the buttons below 👇", reply_markup=home_kb())

    state = d["state"]
    if state == "text":
        if m.content_type == "photo":
            d["photo"] = m.photo[-1].file_id
            d["text"] = m.html_caption or ""
        else:
            d["photo"] = None
            d["text"] = m.html_text if m.entities else m.text
        if not d["text"] and not d["photo"]:
            return ask(chat_id, d, "text", "⚠️ Empty message. Send text or a photo:")
        return show_card(chat_id, d)

    if m.content_type != "text":
        return bot.send_message(chat_id, "⚠️ Please send text.", reply_markup=cancel_kb())

    if state == "btn_name":
        bulk = parse_bulk(m.text)
        if bulk:
            d["buttons"] = (d["buttons"] + bulk)[:MAX_BUTTONS]
            return show_card(chat_id, d)
        d["pending_name"] = m.text.strip()[:64]
        return ask(chat_id, d, "btn_url", f"🔗 Send the <b>URL</b> or <b>@username</b> for "
                   f"“{html.escape(d['pending_name'])}”:")

    if state == "btn_url":
        url = normalize_url(m.text)
        if not url:
            return ask(chat_id, d, "btn_url", "⚠️ Invalid link. Send a valid URL or @username:")
        d["buttons"].append({"name": d["pending_name"], "url": url})
        return show_card(chat_id, d)

    if state == "target":
        target = m.text.strip()
        target = int(target) if re.match(r"^-?\d+$", target) else target
        return publish(chat_id, d, target, m.from_user)


def setup():
    try:
        bot.set_my_commands([BotCommand("start", "Open the bot"), BotCommand("new", "Create a new post"),
                             BotCommand("myposts", "Reuse your recent posts"), BotCommand("cancel", "Discard draft")])
    except Exception as e:
        log.warning("set_my_commands failed: %s", e)
