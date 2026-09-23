"""Supabase data layer — bot aur web dono isi ko use karte hain."""
import json
import logging

from config import SUPABASE_URL, SUPABASE_KEY

log = logging.getLogger("db")

try:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
except Exception as e:  # pragma: no cover
    log.warning("Supabase unavailable: %s", e)
    supabase = None


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        log.error("DB error: %s", e)
        return default


def save_post(user_id: int, username: str, text: str, buttons: list) -> None:
    """Post save karo aur user ka post counter badhao."""
    if not supabase:
        return

    def _run():
        res = supabase.table("users").select("total_posts").eq("id", user_id).execute()
        if res.data:
            total = res.data[0]["total_posts"] + 1
            supabase.table("users").update({"username": username, "total_posts": total}).eq("id", user_id).execute()
        else:
            supabase.table("users").insert({"id": user_id, "username": username, "total_posts": 1}).execute()

        supabase.table("posts").insert({
            "user_id": user_id,
            "message_text": text,
            "btn_name": json.dumps([b["name"] for b in buttons]),
            "btn_url": json.dumps([b["url"] for b in buttons]),
        }).execute()

    _safe(_run, None)


def get_leaderboard(limit: int = 10) -> list:
    if not supabase:
        return []
    return _safe(
        lambda: supabase.table("users").select("id,username,total_posts")
        .order("total_posts", desc=True).limit(limit).execute().data, [])


def get_posts(limit: int = 100) -> list:
    if not supabase:
        return []
    return _safe(
        lambda: supabase.table("posts").select("*")
        .order("created_at", desc=True).limit(limit).execute().data, [])


def get_user_posts(user_id: int, limit: int = 5) -> list:
    if not supabase:
        return []
    return _safe(
        lambda: supabase.table("posts").select("*").eq("user_id", user_id)
        .order("created_at", desc=True).limit(limit).execute().data, [])


def get_stats() -> dict:
    if not supabase:
        return {"users": 0, "posts": 0}
    return _safe(lambda: {
        "users": supabase.table("users").select("id", count="exact").execute().count or 0,
        "posts": supabase.table("posts").select("id", count="exact").execute().count or 0,
    }, {"users": 0, "posts": 0})


def parse_buttons(post: dict) -> list:
    """DB row se buttons list nikalo — purane single-string format ko bhi handle karta hai."""
    try:
        names, urls = json.loads(post["btn_name"]), json.loads(post["btn_url"])
        return [{"name": n, "url": u} for n, u in zip(names, urls)]
    except Exception:
        return [{"name": post.get("btn_name", "Link"), "url": post.get("btn_url", "")}]
