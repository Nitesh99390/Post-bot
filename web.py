"""Flask web server — Mini App + JSON API (initData HMAC verified)."""
import hashlib
import hmac
import json
import re
from urllib.parse import parse_qsl

from flask import Flask, jsonify, render_template, request

import db
from config import BOT_TOKEN, OWNER_ID

app = Flask(__name__)


def verify_init_data(init_data: str) -> dict | None:
    """Telegram WebApp initData verify karo — fake user_id se links leak nahi honge."""
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        received = data.pop("hash", "")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return json.loads(data["user"]) if hmac.compare_digest(calc, received) else None
    except Exception:
        return None


@app.get("/")
def health():
    return jsonify(status="ok", service="post-bot")


@app.get("/app")
@app.get("/stats")
def mini_app():
    return render_template("app.html")


@app.get("/api/data")
def api_data():
    user = verify_init_data(request.headers.get("X-Init-Data", ""))
    uid = user["id"] if user else 0
    is_admin = uid == OWNER_ID

    posts = []
    for p in db.get_posts():
        can_view = is_admin or uid == p["user_id"]
        buttons = db.parse_buttons(p)
        posts.append({
            "id": p["id"],
            "user_id": p["user_id"],
            "created_at": p.get("created_at"),
            "text": p["message_text"],
            "plain": re.sub(r"<[^>]+>", "", p["message_text"]),
            "mine": uid == p["user_id"],
            "buttons": [{"name": b["name"], "url": b["url"] if can_view else None} for b in buttons],
        })

    return jsonify(
        me={"id": uid, "name": user.get("first_name", "") if user else "Guest", "admin": is_admin},
        stats=db.get_stats(),
        leaderboard=db.get_leaderboard(),
        posts=posts,
    )
