from __future__ import annotations

BTN_NEW = "✨ New Post"
BTN_HELP = "ℹ️ Help"
BTN_TEXT = "📝 Text"
BTN_BUTTON = "🔘 Button"
BTN_UNDO = "↩️ Undo"
BTN_DONE = "✅ Publish"
BTN_CANCEL = "✖️ Cancel"
BTN_SKIP = "⏭ Skip"

STYLES: dict[str, tuple[str, str, str]] = {
    "plain": ("Aa Normal", "", ""),
    "bold": ("𝗔𝗮 Bold", "<b>", "</b>"),
    "italic": ("𝘈𝘢 Italic", "<i>", "</i>"),
    "mono": ("𝙰𝚊 Mono", "<code>", "</code>"),
    "quote": ("❝ Quote", "<blockquote>", "</blockquote>"),
}

WELCOME = (
    "<b>Post Maker</b>\n"
    "<i>Create polished posts for channels & groups.</i>\n\n"
    "<blockquote>Media · Styled text · Coloured link buttons</blockquote>\n\n"
    "Tap <b>{new}</b> to begin."
)

HELP = (
    "<b>How it works</b>\n\n"
    "1️⃣  Send a GIF, sticker, photo, video or emoji\n"
    "2️⃣  Add text and choose a font style\n"
    "3️⃣  Add link buttons in red, green or blue\n"
    "4️⃣  Publish and forward anywhere\n\n"
    "<b>Links accepted</b>\n"
    "<code>https://t.me/name</code> · <code>t.me/name</code> · <code>@name</code> · <code>site.com</code>\n\n"
    "<b>Commands</b>\n"
    "/start · /new · /help · /cancel"
)

STEP_MEDIA = (
    "<b>Step 1 · Media</b>\n\n"
    "Send a <b>GIF</b>, <b>sticker</b>, <b>photo</b> or <b>video</b>.\n"
    "<i>Or just send an emoji / short text.</i>"
)

PREVIEW = "<b>Preview</b>  ·  {summary}\n<i>What would you like to add?</i>"

ASK_TEXT = "<b>Text</b>\n\nType your message and send it."
ASK_STYLE = "<b>Font style</b>\n\nPick how the text should look."
ASK_BTN_NAME = "<b>Button label</b>\n\n<i>Example:</i> <code>Join Channel</code>"
ASK_BTN_LINK = "<b>Button link</b>\n\n<i>Example:</i> <code>https://t.me/yourchannel</code>"
ASK_BTN_COLOR = "<b>Button colour</b>"

ERR_NOT_LINK = "That doesn't look like a link.\nTry <code>https://t.me/yourchannel</code> or <code>@username</code>."
ERR_LINK_REJECTED = "Telegram did not accept that link. Please send another one."
ERR_TOO_LONG = "Too long — the limit is <b>{limit}</b> characters."
ERR_EMPTY = "Your post is empty. Add some media, text or a button first."
ERR_MAX_BUTTONS = "You've reached the maximum of <b>{max}</b> buttons."
ERR_GENERIC = "Something went wrong. Send /start to try again."
ERR_NEED_MEDIA = "Please send a GIF, sticker, photo, video or emoji."
ERR_NEED_TEXT = "Please type some text."
ERR_PICK = "Please use the buttons below."

DONE = (
    "<b>Published</b> ✨\n\n"
    "Forward the post above to any channel or group.\n"
    "Tap <b>{new}</b> to create another."
)
CANCELLED = "Cancelled. Tap <b>{new}</b> whenever you're ready."
UNDONE = "Last change removed."
NOTHING_TO_UNDO = "Nothing to undo."
IDLE = "Tap <b>{new}</b> to create a post."
