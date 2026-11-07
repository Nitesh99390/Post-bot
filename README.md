# Post Maker: Telegram Mini App

Compose a post once, then publish it to any number of your groups and channels from a fast Telegram **Mini App**. The bot itself says almost nothing in chat: it shows one "Open Post Maker" button, and everything else happens in the app.

## What you get

- **Compose**: rich text (bold, italic, underline, strike, code, spoiler, quote, links), one attachment (photo, video, GIF, audio or file up to 30 MB), up to 10 coloured link buttons, link-preview switch and a live preview.
- **Groups**: add the bot as an admin to any group or channel and it appears in the app automatically. Keep **one default group**, **select as many as you like**, and send to all of them in one tap.
- **Send with live progress**: per-chat status (delivered, failed, not confirmed), retry only the failed ones, links to the posted messages.
- **Saved posts**: keep up to 30 reusable posts.
- **Profile**: your Telegram name, photo and username, Premium badge, usage stats and sync status.
- Dark and light themes that follow Telegram, animations, haptics, safe-area support.

## Reliability

- Draft is auto-saved while you type (debounced) with a local copy that survives offline or a closed app; the sync chip shows *Synced / Saving / Retrying / Offline* and Telegram asks before closing while changes are unsynced.
- API calls retry with backoff; storage calls retry on 429/5xx.
- Sending uses a per-send `request_id`, so a retried request never posts twice. Network errors whose outcome is unknown are shown as **Not confirmed** and are never blindly resent. Telegram flood limits (`RetryAfter`) are waited out, migrated groups are followed, and one failing chat never stops the others.
- Only an admin who can post in a chat can link it, and this is re-checked when sending.
- Every API request is authenticated by validating Telegram's signed `initData` (HMAC-SHA256 with the bot token). There are no logins and no passwords.

## Setup

1. **Supabase**: open the dashboard → **SQL Editor**, paste `supabase/migrations/20261106000000_mini_app.sql` and click **Run** (safe to re-run; it also creates the older tables). Without it the app falls back to in-memory storage and shows a "Temporary" sync badge.
2. **Deploy** (Render blueprint in `render.yaml`) and set `BOT_TOKEN`. Render provides `RENDER_EXTERNAL_URL`, which is used for the webhook and for the Mini App address `<url>/app/`. The bot sets its own menu button to the Mini App on start.
3. Open the bot in Telegram, press **Post Maker** (menu button) or `/start`.
4. Add the bot as **admin** to a group or channel (the app has buttons that open Telegram's add-bot screen with the right admin rights pre-selected). It shows up in **Groups** within seconds. You can also add a chat by `@username` or `t.me` link.

Optional BotFather step: `/setmenubutton` is not needed; if you want a launch button next to the chat, `/newapp` can register the same URL.

## Run locally

```bash
pip install -r requirements.txt
export BOT_TOKEN=your_bot_token
export WEBHOOK_URL=https://your-public-https-url   # Mini Apps require HTTPS
python main.py
```

Without `WEBHOOK_URL` the bot runs in polling mode and the Mini App button is not configured (Telegram requires an HTTPS address). Set `WEBAPP_URL` to override the address Telegram opens. `PORT` defaults to 10000. Environment variables are read from the process; `.env` is not loaded automatically.

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Required. From @BotFather. |
| `WEBHOOK_URL` / `RENDER_EXTERNAL_URL` | Public HTTPS base URL (webhook + Mini App). |
| `WEBAPP_URL` | Optional override for the Mini App address. |
| `SUPABASE_URL`, `SUPABASE_KEY` | Storage; default to the linked project. Use a `sb_secret_…` key on the server and run the "harden" block at the end of the SQL for tighter security. |
| `STORAGE=memory` | Disable Supabase. |

## Server

One aiohttp process serves `/health`, `/webhook`, the static Mini App under `/app/` and the JSON API under `/api/` (state, draft, media, chats, send, saved posts). Static files are sent with a strict Content-Security-Policy that allows embedding only in Telegram. The webhook uses a token-derived secret, a 256 KiB body limit, validation, a bounded queue and recent-update deduplication. The bot receives `message` and `my_chat_member` updates; the latter keeps the group list current when the bot is added, promoted, removed or its group is upgraded.

Run **one** instance per bot token. Free Render instances sleep and have a cold start; the app shows a retry screen if the server is still waking. Jobs in progress live in memory: a restart marks unfinished chats as failed so you can retry.

## Tests

```bash
python -m unittest discover -s tests -v
```

Offline: fake Telegram bot, in-memory store, mocked Supabase transport and the real aiohttp app via a test client. No token, database or network needed.

### Try the whole UI without a token (development only)

```bash
python tools/devserver.py 8080      # fake bot + demo groups, prints a signed initData
pip install playwright && playwright install chromium
python tools/e2e.py http://localhost:8080 dark   # drives the Mini App end to end, screenshots in /tmp/shots
```

`tools/` is not used in production and `playwright` is not in `requirements.txt`.
