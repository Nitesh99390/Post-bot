"""Simple JSON-file based persistence for channels and scheduled posts.

Render's free tier has an ephemeral filesystem, so this is best-effort.
Attach a Render Disk at DATA_DIR for real persistence.
"""
import json
import os
import threading
from typing import Any

from .config import DATA_DIR

_lock = threading.Lock()


def _path(name: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{name}.json")


def _load(name: str, default: Any) -> Any:
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(name: str, data: Any) -> None:
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(name))


# ---------------------------------------------------------------- channels
# Structure: { "<user_id>": { "<chat_id>": {"title": str, "username": str|None} } }

def get_channels(user_id: int) -> dict[str, dict]:
    with _lock:
        data = _load("channels", {})
        return data.get(str(user_id), {})


def add_channel(user_id: int, chat_id: int, title: str, username: str | None) -> None:
    with _lock:
        data = _load("channels", {})
        user = data.setdefault(str(user_id), {})
        user[str(chat_id)] = {"title": title, "username": username}
        _save("channels", data)


def remove_channel(user_id: int, chat_id: int | str) -> bool:
    with _lock:
        data = _load("channels", {})
        user = data.get(str(user_id), {})
        removed = user.pop(str(chat_id), None) is not None
        _save("channels", data)
        return removed


# ---------------------------------------------------------------- scheduled
# Structure: list of { "id": str, "user_id": int, "chat_ids": [int], "when": iso, "post": {...} }

def get_scheduled(user_id: int | None = None) -> list[dict]:
    with _lock:
        items = _load("scheduled", [])
        if user_id is None:
            return items
        return [i for i in items if i.get("user_id") == user_id]


def add_scheduled(item: dict) -> None:
    with _lock:
        items = _load("scheduled", [])
        items.append(item)
        _save("scheduled", items)


def remove_scheduled(job_id: str) -> bool:
    with _lock:
        items = _load("scheduled", [])
        new_items = [i for i in items if i.get("id") != job_id]
        _save("scheduled", new_items)
        return len(new_items) != len(items)
