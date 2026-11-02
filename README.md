# Post Maker Bot

A Telegram bot that builds polished posts for channels and groups — media, styled text and coloured link buttons — through a simple guided chat flow.

## Flow

```
✨ New Post
  └─ send GIF / sticker / photo / video / emoji        → preview
[📝 Text] [🔘 Button]
[↩️ Undo] [✅ Publish]
[✖️ Cancel]
  ├─ 📝 Text   → type → pick style (Normal · Bold · Italic · Mono · Quote) → preview
  └─ 🔘 Button → label → link → [🔴 Red] [🟢 Green] [🔵 Blue]          → preview
✅ Publish → final post (forward anywhere)
```

- Live preview after every step, unlimited **Undo**, **Cancel** from any step.
- Button colours use Telegram's native button styles.
- Links accepted loosely: `https://t.me/x`, `t.me/x`, `@username`, `site.com`.
- Long captions automatically fall back to media + separate text message.

## Backend

| Feature | Detail |
|---|---|
| Transport | Webhook when a public `https://` URL exists, long polling otherwise |
| Security | Per-token webhook secret, payload validation, private chats only |
| Persistence | Drafts survive restarts (`PicklePersistence`) |
| Resilience | Rate limiter with retries, pooled HTTP client, transient-error filtering |
| Ops | `/health` with uptime, keep-alive pinger for Render free tier, admin start-up alert, graceful shutdown |
| Config | Strict validation of token / port / URL at boot |

## Deploy on Render

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Render → **New → Blueprint** → connect this repo (`render.yaml` is detected).
3. Set **`BOT_TOKEN`** (and optionally **`ADMIN_ID`**).
4. Deploy. Logs show `Webhook → https://<app>.onrender.com/webhook` and `Bot online as @yourbot`.

Render provides `RENDER_EXTERNAL_URL` automatically, so webhook mode is enabled with no extra setup.

## Run locally

```bash
pip install -r requirements.txt
export BOT_TOKEN=123456:ABC...
python main.py                # polling mode
python -m tests.test_flow     # offline end-to-end tests (fake Telegram API)
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `BOT_TOKEN` | — | **Required.** Token from @BotFather |
| `WEBHOOK_URL` | `RENDER_EXTERNAL_URL` | Public https URL → webhook mode |
| `ADMIN_ID` | — | Telegram user id for start-up alerts |
| `PORT` | `10000` | HTTP port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `KEEP_ALIVE` | `true` | Self-ping `/health` in webhook mode |
| `KEEP_ALIVE_INTERVAL` | `600` | Seconds between pings (min 60) |
| `PERSISTENCE_FILE` | `data/state.pickle` | Draft storage path |

## Structure

```
├── main.py              # HTTP server, webhook/polling, lifecycle
├── bot/
│   ├── config.py        # typed settings + validation
│   ├── handlers.py      # state machine, keyboards, session
│   ├── post.py          # Post / Button models, URL normalisation, sending
│   └── texts.py         # all user-facing copy
├── tests/test_flow.py   # offline end-to-end tests
├── render.yaml
└── requirements.txt
```

## License

MIT
