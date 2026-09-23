# 📮 Post Bot

Telegram bot + Mini App to create channel posts with inline URL buttons.

## Structure
| File | Purpose |
|---|---|
| `main.py` | Entry point (Flask + bot polling + keep-alive) |
| `config.py` | Env config |
| `db.py` | Supabase data layer |
| `bot.py` | Inline-keyboard post builder (draft card, bulk buttons, photo, reuse) |
| `web.py` | Mini App routes + verified `/api/data` |
| `templates/app.html` | Dashboard UI (Overview · Leaderboard · Posts) |

## Env vars
`BOT_TOKEN` · `APP_LINK` · `SUPABASE_URL` · `SUPABASE_KEY` · `DEFAULT_CHANNEL` · `OWNER_ID` · `PORT`

## Run
```bash
pip install -r requirements.txt
python main.py
```
