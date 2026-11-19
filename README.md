# Post Studio Bot

A zero-clutter, live-preview Telegram bot for composing text, photos, videos, GIFs, stickers, audio, voice notes, video messages and files with coloured link buttons. Everything updates **in-place** inside a single clean workspace in private chat, backed by cloud-synced drafts, templates and stats via **Supabase**.

## Zero-Clutter Live Studio Workflow

1. Tap **✨ Create Post** (or drop any media / forwarded post directly in chat).
2. **Live Preview + Single Studio Panel**:
   - Your post preview stays right above a single inline **🎛 Post Studio** control card.
   - Editing text, swapping media (`Photo ↔ Video ↔ GIF ↔ Audio ↔ File`), adding/removing coloured buttons, or toggling options edits the **exact same preview message in place** (`editMessageText` / `editMessageCaption` / `editMessageMedia` / `editMessageReplyMarkup`).
   - User input messages are automatically cleaned up once merged into the draft, keeping chat spotless.
3. Tap **✅ Finish** to remove the Studio control card and leave only your finished post ready to forward — or tap **🚀 Publish** to send directly to your linked channel in one click.

## Inline Studio Controls & Shortcuts

| Feature | Usage |
|---|---|
| Live Text / Caption Editor | Tap **✏️ Add/Edit Text** (preserves bold, italic, spoilers, quotes & links) |
| Interactive Button Manager | Tap **🔗 Add Button** or **🎛 Buttons** to cycle colours (`🔵 → 🟢 → 🔴`) & delete individual buttons |
| Fast Batch Buttons | Send `Label - link` or `Join - @mychannel && Website \| example.com` (up to 3 per row) |
| Live Options Panel | Tap **⚙️ Options** to toggle Link Preview, Grid (`1/2/3 per row`), Spoiler blur, Top/Bottom caption, Content Protection & Silent mode |
| Undo History | Tap **↩️ Undo** or `/undo` (up to 10 steps) |
| Cloud Templates | Tap **💾 Save** or `/posts` (interactive 1-tap 📂 Open & 🗑 Delete buttons, up to 30 templates) |
| 1-Tap Channel Publish | Set `/channel @name` once, then tap **🚀 Publish** in Studio or run `/publish [pin]` |
| Import Existing Posts | Forward any post — media, formatting, spoilers and link button rows are imported automatically |

## Run Locally

```bash
pip install -r requirements.txt
export BOT_TOKEN=your_bot_token
python main.py
```

Without `WEBHOOK_URL` / `RENDER_EXTERNAL_URL`, the bot runs in polling mode while serving `/health` on `PORT` (default `10000`). Set `WEBHOOK_URL` to a public HTTPS URL to enable authenticated webhook mode (`message` + `callback_query`).

## Supabase Setup

1. Open the Supabase SQL Editor and run `supabase/migrations/20261104000000_post_bot.sql` (idempotent).
2. Override `SUPABASE_URL` and `SUPABASE_KEY` via environment variables if using your own Supabase project, or set `STORAGE=memory` to run in-memory only.

## Render Deployment

Connect the repository as a Blueprint using `render.yaml` and set `BOT_TOKEN`. Render provides `RENDER_EXTERNAL_URL` automatically.

## Tests

```bash
python -m unittest discover -s tests -v
```
