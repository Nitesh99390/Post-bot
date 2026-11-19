# Post Maker Bot

A clean, fast Telegram bot for composing text, photos, videos, GIFs, stickers, audio, voice notes, video messages and files with coloured link buttons. Everything runs directly in private chat with cloud-synced drafts, templates and stats powered by **Supabase**.

## Workflow

1. Tap **Create Post** (or drop media/forwarded posts directly in chat).
2. Refine with **Edit Text**, **Add Button** and **Preview**.
3. Tap **Finish** to get the shareable post, or run `/publish` to send straight to your channel.

The on-screen keyboard stays minimal so it never feels cluttered: **Create Post**, then **Edit Text / Add Button / Preview / Finish** (plus **Remove Last Button** when buttons exist). Advanced controls live in clean slash commands and smart input:

| Feature | Usage |
|---|---|
| Undo last change | `/undo` (up to 10 steps) |
| Clear specific parts | `/clear text`, `/clear media`, or `/clear buttons` |
| Multi-column button grid | `/layout 1`, `/layout 2`, or `/layout 3` (cycles when called without number) |
| Side-by-side quick buttons | `Join - @mychannel && Website \| example.com` (up to 3 per row) |
| Batch buttons | Send multiple `Label - link` or `Label \| link` lines at once |
| Media spoiler blur | `/spoiler` (for photos, videos and GIFs) |
| Caption position | `/caption` (places caption above or below media) |
| Content protection | `/protect` (blocks forwarding and saving) |
| Silent delivery | `/silent` (sends without notification sound) |
| Link preview | `/linkpreview` |
| Save template | `/save name` (defaults to the first line of text) |
| Saved templates | `/posts`, then `/open_ID` or `/del_ID` (up to 30) |
| Direct channel publish | `/channel @name` once (bot & user must be admins), then `/publish` or `/publish pin` |
| Copy any post | Forward an existing post — media, formatting, spoilers and button rows are imported |
| Stats | `/stats` and `/start` |

## Run Locally

```bash
pip install -r requirements.txt
export BOT_TOKEN=your_bot_token
python main.py
```

Without `WEBHOOK_URL` / `RENDER_EXTERNAL_URL`, the bot runs in polling mode while still serving `/health` on `PORT` (default `10000`). Set `WEBHOOK_URL` to a public HTTPS URL to enable authenticated webhook mode.

## Supabase Setup

1. Open the Supabase SQL Editor and run `supabase/migrations/20261104000000_post_bot.sql` (idempotent).
2. Override `SUPABASE_URL` and `SUPABASE_KEY` via environment variables if using your own Supabase project, or set `STORAGE=memory` to run in-memory only.

## Render Deployment

Connect the repository as a Blueprint using `render.yaml` and set `BOT_TOKEN`. Render provides `RENDER_EXTERNAL_URL` automatically.

## Tests

```bash
python -m unittest discover -s tests -v
```
