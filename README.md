# ✨ Post Maker Bot

A super-simple Telegram bot that makes beautiful posts with **GIF, stickers, emojis, text** and **colourful buttons** 🌈 — so easy a kid can use it. Comes with a colourful **Mini App** and is ready for **Render**.

## 🎯 How it works (only a few taps)

```
✨ Create Post
   └─ send a GIF / Sticker / Emoji (photo/video also OK)   → 👀 preview
[📝 Add Text]  [🔘 Add Button]
[✅ Done]
   ├─ 📝 Add Text   → keyboard hides → type text            → 👀 preview
   └─ 🔘 Add Button → keyboard hides → button name → link
                    → [🔴 Red] [🟢 Green] [🔵 Blue]          → 👀 preview
✅ Done → final post (forward it anywhere) → back to start
```

- After **every step** the bot sends the post as it looks so far.
- Button colours use Telegram's native button styles (Bot API 9.4+).
- Links can be typed loosely: `https://t.me/x`, `t.me/x`, `@username`, `example.com`.

### 🎨 Mini App
Tap **🎨 Mini App** → pick emojis, write text, add red/green/blue buttons with a live preview → **🚀 Send to Bot**. The bot sends the post back and you can still add a GIF/sticker or more text/buttons in chat.

## 🚀 Deploy on Render

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. On [Render](https://render.com) → **New → Blueprint** (or Web Service) → connect this repo. `render.yaml` is detected automatically.
3. Add the environment variable **`BOT_TOKEN`** = your token.
4. Deploy. Logs show `Webhook mode: https://<app>.onrender.com/webhook` and `Bot started as @yourbot`.

That's it — no other settings needed:
- Render sets `RENDER_EXTERNAL_URL` automatically → the bot uses a **webhook**, so a sleeping free instance **wakes up** when someone messages the bot (first reply may take ~30-50 s after sleep).
- The Mini App is served at `https://<app>.onrender.com/app` and its button appears automatically.

## 🧑‍💻 Run locally

```bash
pip install -r requirements.txt
export BOT_TOKEN=123456:ABC...
python main.py          # polling mode (Mini App button hidden without a public https URL)
```
Set `WEBHOOK_URL=https://your-public-url` to test webhook + Mini App locally (e.g. with a tunnel).

Test the full flow offline (fake Telegram API):
```bash
python -m tests.test_flow
```

## 🗂 Project structure

```
├── main.py            # web server: /health, /app (Mini App), /webhook  (+ polling fallback)
├── bot/
│   ├── config.py      # BOT_TOKEN, PORT, public URL
│   ├── handlers.py    # the whole step-by-step flow + Mini App data
│   └── post.py        # Post model, coloured buttons, sending logic
├── webapp/index.html  # colourful Mini App
├── tests/test_flow.py # end-to-end flow test
├── render.yaml
└── requirements.txt
```

## 📄 License
MIT
