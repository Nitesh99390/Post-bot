# 📢 Telegram Post Bot

A feature-rich Telegram bot for creating and publishing posts to channels/groups — with media, formatted text, inline URL buttons, scheduling and more. Built with [python-telegram-bot v21](https://python-telegram-bot.org/) and ready to deploy on **Render**.

## ✨ Features

| Feature | Description |
|---|---|
| 📝 Rich content | Text, photo, video, GIF, document, audio — formatting (bold/italic/links/spoilers) preserved |
| 🔘 Inline buttons | Multiple rows of URL buttons with a simple text syntax |
| 👁 Preview | See exactly how the post will look before publishing |
| 📢 Multi-channel | Add unlimited channels/groups; post to one or all at once |
| ⏰ Scheduling | `18:30`, `2025-12-31 18:30`, `+30m`, `+2h`, `+1d` — survives restarts |
| ⚙️ Options | No link preview · Silent · Protect content · Auto-pin |
| 🔐 Admin lock | Restrict bot to specific user IDs via `ADMIN_IDS` |
| 🩺 Health endpoint | `/health` for Render's web-service health checks |

## 🚀 Deploy on Render

1. **Create a bot** with [@BotFather](https://t.me/BotFather) → copy the token.
2. Push this repo to GitHub.
3. On [Render](https://render.com) → **New → Web Service** → connect the repo.
   - Render auto-detects `render.yaml` (Python, `python main.py`, health check `/health`).
4. In **Environment** add:

   | Key | Value |
   |---|---|
   | `BOT_TOKEN` | *(your BotFather token)* — **required** |
   | `ADMIN_IDS` | `123456789,987654321` — optional, your Telegram user IDs |
   | `TZ` | `Asia/Kolkata` — optional, timezone for scheduling |

5. Deploy. Logs should show `Bot started as @yourbot`.

> **Free tier note:** Render free web services sleep after 15 min of inactivity. Use an uptime pinger (e.g. UptimeRobot) hitting `https://<your-app>.onrender.com/health` every 5–10 min to keep it awake, or use a paid plan. Scheduled posts are stored in `data/` — attach a Render Disk at `/opt/render/project/src/data` (or set `DATA_DIR`) for persistence across deploys.

## 🧑‍💻 Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # edit BOT_TOKEN
export $(grep -v '^#' .env | xargs)
python main.py
```

## 📖 Usage

1. **Add the bot as admin** in your channel (with *Post Messages* permission).
2. `/addchannel` → forward any message from the channel (or send `@username` / `-100…` ID).
3. `/newpost` → send your content (text or media with caption).
4. Tap **🔘 Buttons** and send:
   ```
   Join Channel - https://t.me/example
   Website - https://example.com | Contact - https://t.me/someone
   ```
   (one row per line, `|` separates buttons in the same row)
5. Toggle options, tap **👁 Preview**, then **📤 Send Now** or **⏰ Schedule**.

### Commands

| Command | Action |
|---|---|
| `/newpost` | Start creating a post |
| `/addchannel` | Add a channel/group |
| `/channels` | List / remove channels |
| `/scheduled` | List / cancel scheduled posts |
| `/myid` | Show your user ID (for `ADMIN_IDS`) |
| `/help` | Full instructions |
| `/cancel` | Abort current action |

## 🗂 Project structure

```
├── main.py              # Entry: bot polling + aiohttp health server
├── bot/
│   ├── config.py        # Env-var config (BOT_TOKEN, ADMIN_IDS, PORT, TZ)
│   ├── handlers.py      # Commands, editor UI, callbacks, scheduling
│   ├── post.py          # Post model, button parser, send logic
│   └── storage.py       # JSON persistence (channels, scheduled posts)
├── render.yaml          # Render blueprint
├── requirements.txt
└── .env.example
```

## 📄 License

MIT
