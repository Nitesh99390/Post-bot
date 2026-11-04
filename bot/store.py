"""Persistence for drafts, saved posts and user stats.

``SupabaseStore`` talks to Supabase's REST API (PostgREST) with httpx, which is
already installed as a python-telegram-bot dependency. ``MemoryStore`` keeps
the same interface in-process and is used for tests or when Supabase is not
reachable, so the bot never stops working because of storage.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)
MAX_SAVED_POSTS = 30
MAX_NAME = 40


class StoreError(RuntimeError):
    """Raised when the storage backend cannot complete a request."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    return name[:MAX_NAME].strip()


class MemoryStore:
    name = "memory"

    def __init__(self) -> None:
        self.sessions: dict[int, dict[str, Any]] = {}
        self.users: dict[int, dict[str, Any]] = {}
        self.posts: dict[int, dict[str, Any]] = {}
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

    async def increment_posts(self, user_id: int) -> int:
        row = self.users.setdefault(user_id, {"user_id": user_id, "posts_created": 0})
        row["posts_created"] = int(row.get("posts_created") or 0) + 1
        return row["posts_created"]

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
    ) -> Any:
        headers = {"Prefer": prefer} if prefer else None
        try:
            response = await self._client.request(
                method, path, params=params, json=json, headers=headers
            )
        except httpx.HTTPError as error:
            raise StoreError(f"network: {type(error).__name__}") from None
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
        try:
            for table in ("bot_users", "bot_sessions", "saved_posts"):
                await self._request("GET", f"/{table}", params={"select": "*", "limit": "1"})
        except StoreError as error:
            logger.warning(
                "Supabase unavailable (%s). Run supabase/migrations/*.sql in the "
                "Supabase SQL editor. Falling back to memory storage.",
                error,
            )
            return False
        return True

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

    async def increment_posts(self, user_id: int) -> int:
        # Updates are processed sequentially, so read-modify-write is safe.
        count = int((await self.get_profile(user_id)).get("posts_created") or 0) + 1
        await self.update_profile(user_id, posts_created=count)
        return count

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
