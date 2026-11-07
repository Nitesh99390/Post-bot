"""Persistence for drafts, saved posts and user stats.

``SupabaseStore`` talks to Supabase's REST API (PostgREST) with httpx, which is
already installed as a python-telegram-bot dependency. ``MemoryStore`` keeps
the same interface in-process and is used for tests or when Supabase is not
reachable, so the bot never stops working because of storage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)
MAX_SAVED_POSTS = 30
MAX_NAME = 40
MAX_CHATS = 100
USER_FIELDS = ("first_name", "last_name", "username", "language_code", "photo_url", "is_premium")
CHAT_FIELDS = ("type", "title", "username", "can_post")


class StoreError(RuntimeError):
    """Raised when the storage backend cannot complete a request."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    return name[:MAX_NAME].strip()


def _merge_chats(links: list[dict[str, Any]], chats: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine a user's links with chat details; default first, then by title."""
    rows = []
    for link in links:
        chat = chats.get(link["chat_id"])
        if not chat:
            continue
        rows.append(
            {
                "chat_id": link["chat_id"],
                "is_default": bool(link.get("is_default")),
                "selected": bool(link.get("selected")),
                "type": chat.get("type") or "group",
                "title": chat.get("title") or str(link["chat_id"]),
                "username": chat.get("username"),
                "can_post": bool(chat.get("can_post")),
            }
        )
    rows.sort(key=lambda r: (not r["is_default"], r["title"].lower(), r["chat_id"]))
    # Exactly one default: if several rows were written concurrently keep the first.
    seen = False
    for row in rows:
        if row["is_default"] and seen:
            row["is_default"] = False
        seen = seen or row["is_default"]
    return rows


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self.sessions: dict[int, dict[str, Any]] = {}
        self.users: dict[int, dict[str, Any]] = {}
        self.posts: dict[int, dict[str, Any]] = {}
        self.chats: dict[int, dict[str, Any]] = {}
        self.links: dict[tuple[int, int], dict[str, Any]] = {}
        self._next_id = 1

    async def setup(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    # sessions ------------------------------------------------------------
    async def load_session(self, user_id: int) -> dict[str, Any] | None:
        return self.sessions.get(user_id)

    async def save_session(self, user_id: int, data: dict[str, Any]) -> None:
        self.sessions[user_id] = data

    async def delete_session(self, user_id: int) -> None:
        self.sessions.pop(user_id, None)

    # users ---------------------------------------------------------------
    async def touch_user(self, user_id: int, info: dict[str, Any]) -> None:
        row = self.users.setdefault(
            user_id,
            {"user_id": user_id, "posts_created": 0, "created_at": _now()},
        )
        row.update(info, last_seen=_now())

    async def get_profile(self, user_id: int) -> dict[str, Any]:
        return dict(self.users.get(user_id) or {"user_id": user_id, "posts_created": 0})

    async def update_profile(self, user_id: int, **fields: Any) -> None:
        self.users.setdefault(user_id, {"user_id": user_id, "posts_created": 0}).update(
            fields
        )

    async def increment_posts(self, user_id: int, deliveries: int = 0) -> int:
        row = self.users.setdefault(user_id, {"user_id": user_id, "posts_created": 0})
        row["posts_created"] = int(row.get("posts_created") or 0) + 1
        row["deliveries"] = int(row.get("deliveries") or 0) + deliveries
        return row["posts_created"]

    # chats ---------------------------------------------------------------
    async def upsert_chat(self, chat_id: int, info: dict[str, Any]) -> None:
        row = self.chats.setdefault(chat_id, {"chat_id": chat_id})
        row.update({k: v for k, v in info.items() if k in CHAT_FIELDS}, updated_at=_now())

    async def get_chat(self, chat_id: int) -> dict[str, Any] | None:
        row = self.chats.get(chat_id)
        return dict(row) if row else None

    async def list_user_chats(self, user_id: int) -> list[dict[str, Any]]:
        links = [dict(v) for (u, _), v in self.links.items() if u == user_id]
        return _merge_chats(links, self.chats)

    async def link_chat(self, user_id: int, chat_id: int) -> bool:
        """Link a chat to a user. The first one becomes the default."""
        if (user_id, chat_id) in self.links:
            return False
        mine = [k for k in self.links if k[0] == user_id]
        if len(mine) >= MAX_CHATS:
            raise StoreError("limit")
        first = not mine
        self.links[(user_id, chat_id)] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "is_default": first,
            "selected": first,
        }
        return True

    async def unlink_chat(self, user_id: int, chat_id: int) -> None:
        link = self.links.pop((user_id, chat_id), None)
        if link and link["is_default"]:
            rest = await self.list_user_chats(user_id)
            if rest:
                await self.set_default(user_id, rest[0]["chat_id"])

    async def set_default(self, user_id: int, chat_id: int) -> bool:
        if (user_id, chat_id) not in self.links:
            return False
        for (u, _), link in self.links.items():
            if u == user_id:
                link["is_default"] = False
        self.links[(user_id, chat_id)].update(is_default=True, selected=True)
        return True

    async def set_selection(self, user_id: int, chat_ids: list[int]) -> None:
        chosen = set(chat_ids)
        for (u, c), link in self.links.items():
            if u == user_id:
                link["selected"] = c in chosen

    async def drop_chat(self, chat_id: int) -> None:
        """The bot left a chat: forget it for every user."""
        self.chats.pop(chat_id, None)
        for key in [k for k in self.links if k[1] == chat_id]:
            await self.unlink_chat(*key)

    async def migrate_chat(self, old_id: int, new_id: int) -> None:
        if old_id in self.chats:
            self.chats[new_id] = {**self.chats.pop(old_id), "chat_id": new_id}
        for (u, c) in [k for k in self.links if k[1] == old_id]:
            link = self.links.pop((u, c))
            if (u, new_id) not in self.links:
                self.links[(u, new_id)] = {**link, "chat_id": new_id}

    # saved posts ---------------------------------------------------------
    async def list_posts(self, user_id: int) -> list[dict[str, Any]]:
        rows = [dict(r) for r in self.posts.values() if r["user_id"] == user_id]
        return sorted(rows, key=lambda r: (r["updated_at"], r["id"]), reverse=True)

    async def save_post(self, user_id: int, name: str, post: dict[str, Any]) -> tuple[int, bool]:
        for row in self.posts.values():
            if row["user_id"] == user_id and row["name"].lower() == name.lower():
                row.update(post=post, name=name, updated_at=_now() + f"#{time.monotonic_ns()}")
                return row["id"], True
        if len(await self.list_posts(user_id)) >= MAX_SAVED_POSTS:
            raise StoreError("limit")
        post_id, self._next_id = self._next_id, self._next_id + 1
        stamp = _now() + f"#{time.monotonic_ns()}"
        self.posts[post_id] = {
            "id": post_id,
            "user_id": user_id,
            "name": name,
            "post": post,
            "created_at": stamp,
            "updated_at": stamp,
        }
        return post_id, False

    async def get_post(self, user_id: int, post_id: int) -> dict[str, Any] | None:
        row = self.posts.get(post_id)
        return dict(row) if row and row["user_id"] == user_id else None

    async def delete_post(self, user_id: int, post_id: int) -> bool:
        if await self.get_post(user_id, post_id):
            del self.posts[post_id]
            return True
        return False


class SupabaseStore:
    name = "supabase"

    def __init__(self, url: str, key: str, timeout: float = 8.0) -> None:
        headers = {"apikey": key, "Content-Type": "application/json"}
        # Legacy anon/service_role keys are JWTs and must also be sent as a
        # bearer token; new sb_publishable_/sb_secret_ keys only need apikey.
        if key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        self._client = httpx.AsyncClient(
            base_url=url.rstrip("/") + "/rest/v1",
            headers=headers,
            timeout=timeout,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
        retries: int = 2,
    ) -> Any:
        """One REST call. Transient failures are retried with a short backoff.

        Pass ``retries=0`` for requests that are not idempotent (plain inserts).
        """
        headers = {"Prefer": prefer} if prefer else None
        attempt = 0
        while True:
            try:
                response = await self._client.request(
                    method, path, params=params, json=json, headers=headers
                )
                transient = response.status_code in (429, 500, 502, 503, 504)
                error: str | None = None
            except httpx.HTTPError as exc:
                response, transient = None, True
                error = f"network: {type(exc).__name__}"
            if not transient or attempt >= retries:
                break
            attempt += 1
            await asyncio.sleep(0.25 * attempt)
        if response is None:
            raise StoreError(error or "network")
        if response.status_code >= 400:
            try:
                detail = response.json().get("message", "")
            except ValueError:
                detail = ""
            raise StoreError(f"HTTP {response.status_code} {detail}".strip())
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    async def setup(self) -> bool:
        wanted = {
            "bot_users": "user_id," + ",".join(USER_FIELDS) + ",posts_created,deliveries",
            "bot_sessions": "user_id,data,updated_at",
            "saved_posts": "id,user_id,name,post",
            "bot_chats": "chat_id," + ",".join(CHAT_FIELDS),
            "user_chats": "user_id,chat_id,is_default,selected",
        }
        for attempt in range(3):
            try:
                for table, columns in wanted.items():
                    await self._request(
                        "GET",
                        f"/{table}",
                        params={"select": columns, "limit": "1"},
                        retries=0,
                    )
                return True
            except StoreError as error:
                # 4xx means the schema is missing/outdated: retrying cannot help.
                if str(error).startswith("HTTP 4") or attempt == 2:
                    logger.warning(
                        "Supabase unavailable (%s). Run supabase/migrations/"
                        "20261106000000_mini_app.sql in the Supabase SQL editor. "
                        "Falling back to memory storage.",
                        error,
                    )
                    return False
                await asyncio.sleep(1 + attempt)
        return False

    async def close(self) -> None:
        await self._client.aclose()

    # sessions ------------------------------------------------------------
    async def load_session(self, user_id: int) -> dict[str, Any] | None:
        rows = await self._request(
            "GET",
            "/bot_sessions",
            params={"select": "data", "user_id": f"eq.{user_id}", "limit": "1"},
        )
        return rows[0]["data"] if rows else None

    async def save_session(self, user_id: int, data: dict[str, Any]) -> None:
        await self._request(
            "POST",
            "/bot_sessions",
            params={"on_conflict": "user_id"},
            json={"user_id": user_id, "data": data, "updated_at": _now()},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def delete_session(self, user_id: int) -> None:
        await self._request(
            "DELETE", "/bot_sessions", params={"user_id": f"eq.{user_id}"}
        )

    # users ---------------------------------------------------------------
    async def touch_user(self, user_id: int, info: dict[str, Any]) -> None:
        await self._request(
            "POST",
            "/bot_users",
            params={"on_conflict": "user_id"},
            json={"user_id": user_id, **info, "last_seen": _now()},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def get_profile(self, user_id: int) -> dict[str, Any]:
        rows = await self._request(
            "GET",
            "/bot_users",
            params={"select": "*", "user_id": f"eq.{user_id}", "limit": "1"},
        )
        return rows[0] if rows else {"user_id": user_id, "posts_created": 0}

    async def update_profile(self, user_id: int, **fields: Any) -> None:
        await self._request(
            "PATCH",
            "/bot_users",
            params={"user_id": f"eq.{user_id}"},
            json=fields,
            prefer="return=minimal",
        )

    async def increment_posts(self, user_id: int, deliveries: int = 0) -> int:
        # Callers hold a per-user lock, so read-modify-write is safe.
        row = await self.get_profile(user_id)
        count = int(row.get("posts_created") or 0) + 1
        total = int(row.get("deliveries") or 0) + deliveries
        await self._request(
            "POST",
            "/bot_users",
            params={"on_conflict": "user_id"},
            json={"user_id": user_id, "posts_created": count, "deliveries": total},
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return count

    # chats ---------------------------------------------------------------
    async def upsert_chat(self, chat_id: int, info: dict[str, Any]) -> None:
        await self._request(
            "POST",
            "/bot_chats",
            params={"on_conflict": "chat_id"},
            json={
                "chat_id": chat_id,
                **{k: v for k, v in info.items() if k in CHAT_FIELDS},
                "updated_at": _now(),
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def get_chat(self, chat_id: int) -> dict[str, Any] | None:
        rows = await self._request(
            "GET",
            "/bot_chats",
            params={"select": "*", "chat_id": f"eq.{chat_id}", "limit": "1"},
        )
        return rows[0] if rows else None

    async def _links(self, user_id: int) -> list[dict[str, Any]]:
        return (
            await self._request(
                "GET",
                "/user_chats",
                params={
                    "select": "chat_id,is_default,selected",
                    "user_id": f"eq.{user_id}",
                    "limit": str(MAX_CHATS + 20),
                },
            )
            or []
        )

    async def list_user_chats(self, user_id: int) -> list[dict[str, Any]]:
        links = await self._links(user_id)
        if not links:
            return []
        ids = ",".join(str(link["chat_id"]) for link in links)
        rows = await self._request(
            "GET",
            "/bot_chats",
            params={"select": "*", "chat_id": f"in.({ids})", "limit": str(len(links))},
        )
        return _merge_chats(links, {row["chat_id"]: row for row in rows or []})

    async def link_chat(self, user_id: int, chat_id: int) -> bool:
        links = await self._links(user_id)
        if any(link["chat_id"] == chat_id for link in links):
            return False
        if len(links) >= MAX_CHATS:
            raise StoreError("limit")
        first = not links
        await self._request(
            "POST",
            "/user_chats",
            params={"on_conflict": "user_id,chat_id"},
            json={
                "user_id": user_id,
                "chat_id": chat_id,
                "is_default": first,
                "selected": first,
            },
            prefer="resolution=ignore-duplicates,return=minimal",
        )
        return True

    async def unlink_chat(self, user_id: int, chat_id: int) -> None:
        links = await self._links(user_id)
        was_default = any(l["chat_id"] == chat_id and l.get("is_default") for l in links)
        await self._request(
            "DELETE",
            "/user_chats",
            params={"user_id": f"eq.{user_id}", "chat_id": f"eq.{chat_id}"},
        )
        if was_default:
            rest = await self.list_user_chats(user_id)
            if rest:
                await self.set_default(user_id, rest[0]["chat_id"])

    async def set_default(self, user_id: int, chat_id: int) -> bool:
        links = await self._links(user_id)
        if not any(link["chat_id"] == chat_id for link in links):
            return False
        # Set the new default first so a failure never leaves the user without one.
        await self._request(
            "PATCH",
            "/user_chats",
            params={"user_id": f"eq.{user_id}", "chat_id": f"eq.{chat_id}"},
            json={"is_default": True, "selected": True},
            prefer="return=minimal",
        )
        await self._request(
            "PATCH",
            "/user_chats",
            params={"user_id": f"eq.{user_id}", "chat_id": f"neq.{chat_id}"},
            json={"is_default": False},
            prefer="return=minimal",
        )
        return True

    async def set_selection(self, user_id: int, chat_ids: list[int]) -> None:
        if chat_ids:
            ids = ",".join(str(c) for c in chat_ids)
            await self._request(
                "PATCH",
                "/user_chats",
                params={"user_id": f"eq.{user_id}", "chat_id": f"in.({ids})"},
                json={"selected": True},
                prefer="return=minimal",
            )
            rest = {"user_id": f"eq.{user_id}", "chat_id": f"not.in.({ids})"}
        else:
            rest = {"user_id": f"eq.{user_id}"}
        await self._request(
            "PATCH", "/user_chats", params=rest, json={"selected": False}, prefer="return=minimal"
        )

    async def drop_chat(self, chat_id: int) -> None:
        users = await self._request(
            "GET",
            "/user_chats",
            params={"select": "user_id,is_default", "chat_id": f"eq.{chat_id}"},
        )
        await self._request("DELETE", "/user_chats", params={"chat_id": f"eq.{chat_id}"})
        await self._request("DELETE", "/bot_chats", params={"chat_id": f"eq.{chat_id}"})
        for link in users or []:
            if link.get("is_default"):  # promote another chat for that user
                rest = await self.list_user_chats(link["user_id"])
                if rest:
                    await self.set_default(link["user_id"], rest[0]["chat_id"])

    async def migrate_chat(self, old_id: int, new_id: int) -> None:
        """A group upgraded to a supergroup got a new id; follow it."""
        chat = await self.get_chat(old_id)
        if chat:
            await self.upsert_chat(new_id, chat)
        users = await self._request(
            "GET", "/user_chats", params={"select": "*", "chat_id": f"eq.{old_id}"}
        )
        for link in users or []:
            await self._request(
                "POST",
                "/user_chats",
                params={"on_conflict": "user_id,chat_id"},
                json={**link, "chat_id": new_id},
                prefer="resolution=ignore-duplicates,return=minimal",
            )
        await self._request("DELETE", "/user_chats", params={"chat_id": f"eq.{old_id}"})
        await self._request("DELETE", "/bot_chats", params={"chat_id": f"eq.{old_id}"})

    # saved posts ---------------------------------------------------------
    async def list_posts(self, user_id: int) -> list[dict[str, Any]]:
        return (
            await self._request(
                "GET",
                "/saved_posts",
                params={
                    "select": "id,name,post,updated_at",
                    "user_id": f"eq.{user_id}",
                    "order": "updated_at.desc,id.desc",
                    "limit": str(MAX_SAVED_POSTS),
                },
            )
            or []
        )

    async def save_post(self, user_id: int, name: str, post: dict[str, Any]) -> tuple[int, bool]:
        rows = await self.list_posts(user_id)
        existing = [r for r in rows if r["name"].lower() == name.lower()]
        if existing:
            post_id = existing[0]["id"]
            await self._request(
                "PATCH",
                "/saved_posts",
                params={"id": f"eq.{post_id}", "user_id": f"eq.{user_id}"},
                json={"name": name, "post": post, "updated_at": _now()},
                prefer="return=minimal",
            )
            return post_id, True
        if len(rows) >= MAX_SAVED_POSTS:
            raise StoreError("limit")
        rows = await self._request(
            "POST",
            "/saved_posts",
            json={"user_id": user_id, "name": name, "post": post},
            prefer="return=representation",
            retries=0,
        )
        return rows[0]["id"], False

    async def get_post(self, user_id: int, post_id: int) -> dict[str, Any] | None:
        rows = await self._request(
            "GET",
            "/saved_posts",
            params={
                "select": "id,name,post,updated_at",
                "id": f"eq.{post_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def delete_post(self, user_id: int, post_id: int) -> bool:
        rows = await self._request(
            "DELETE",
            "/saved_posts",
            params={"id": f"eq.{post_id}", "user_id": f"eq.{user_id}"},
            prefer="return=representation",
        )
        return bool(rows)


async def create_store(url: str, key: str, enabled: bool = True) -> MemoryStore | SupabaseStore:
    if enabled and url and key:
        store = SupabaseStore(url, key)
        if await store.setup():
            logger.info("Storage: Supabase")
            return store
        await store.close()
    logger.info("Storage: in-memory (drafts are lost on restart)")
    return MemoryStore()
