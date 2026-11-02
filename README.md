# Post Maker Bot

A focused Telegram bot for composing text, photos, videos, GIFs and stickers with styled link buttons. No frontend or separate app; everything happens in private chat.

## Workflow

1. Choose **Create Post** and send text or media.
2. Use **Edit Text**, **Add Button** and **Preview** to refine the draft.
3. Choose **Finish** and forward the result to a channel or group.

Text formatting is preserved. Telegram controls the chat font; headings use native bold and italic rather than decorative Unicode. Buttons support blue, green and red styles on compatible Telegram clients.

`/new` starts a fresh post, `/back` leaves the current step without discarding the post, `/preview` shows the draft, `/cancel` discards it, and `/help` explains the flow. **Remove Last Button** lets you undo a button, including a link rejected by Telegram. Edit Text replaces the full text. Sending media from the editor replaces the media and uses its caption, if supplied.

Stickers with text and media with text exceeding the caption limit are sent as two messages. Forward both messages. Text is limited to 4,000 UTF-16 units (some symbols count as two), with up to 10 buttons. Links accept HTTP(S), bare domains and @channel names; other schemes and credential-bearing URLs are rejected.

## Run

```bash
pip install -r requirements.txt
export BOT_TOKEN=your_bot_token
python main.py
```

Environment variables are read from the process; `.env` files are not loaded automatically. Without a public URL the bot uses polling. Set `WEBHOOK_URL` to a public HTTPS base URL to use webhooks. `PORT` defaults to 10000.

## Render

Connect this repository as a Blueprint and set `BOT_TOKEN`. The existing `render.yaml` configures the Python service and health check. Render supplies `RENDER_EXTERNAL_URL` automatically. Run only one service instance per bot token.

Only `/`, `/health` and (in webhook mode) `/webhook` are served. Health returns 503 until the application starts. Webhooks use a token-derived secret, a 256 KiB body limit, validation, a bounded queue and recent-update deduplication. Saturation returns 503 so Telegram can retry. Pending updates are not deliberately dropped on startup. The Telegram menu button is reset to native commands.

Drafts, queued updates and the recent-update cache are held in memory, not a database. Restarting loses them; deduplication is not an exactly-once delivery guarantee. Delivery failures retain the draft while the process is running. Ambiguous network failures are not automatically resent: check the chat before retrying. Free Render instances can sleep and have a cold-start delay. Previously configured BotFather profile/launch buttons and chat-specific menu overrides must be removed separately in Telegram if present.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use a fake Telegram transport. No real token or outbound Telegram calls are required.
