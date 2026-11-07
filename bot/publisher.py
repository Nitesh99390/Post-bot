"""Send one post to many chats with live progress, retries and no duplicates."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from telegram import Bot
from telegram.error import (
    BadRequest,
    ChatMigrated,
    Forbidden,
    NetworkError,
    RetryAfter,
    TelegramError,
)

from .chats import user_can_publish
from .post import PartialSend, Post
from .store import StoreError

logger = logging.getLogger(__name__)

CONCURRENCY = 4
MAX_RETRY_WAIT = 30
JOB_TTL = 30 * 60

QUEUED, SENDING, OK, FAILED, UNCONFIRMED, PARTIAL = (
    "queued", "sending", "ok", "failed", "unconfirmed", "partial",
)
FINAL = {OK, FAILED, UNCONFIRMED, PARTIAL}


class Busy(Exception):
    """The user already has a send in progress."""


class NoTargets(Exception):
    """None of the requested chats belongs to the user."""


@dataclass
class Job:
    id: str
    user_id: int
    post: Post
    request_id: str
    results: dict[int, dict[str, Any]]
    created: float = field(default_factory=time.monotonic)
    done: bool = False

    def snapshot(self) -> dict[str, Any]:
        rows = list(self.results.values())
        return {
            "id": self.id,
            "done": self.done,
            "total": len(rows),
            "ok": sum(r["status"] == OK for r in rows),
            "failed": sum(r["status"] in (FAILED, PARTIAL) for r in rows),
            "unconfirmed": sum(r["status"] == UNCONFIRMED for r in rows),
            "results": rows,
        }


def message_url(chat: dict[str, Any], message_id: int | None) -> str | None:
    if not message_id:
        return None
    if chat.get("username"):
        return f"https://t.me/{chat['username']}/{message_id}"
    chat_id = int(chat["chat_id"])
    if str(chat_id).startswith("-100"):
        return f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"
    return None


def explain(error: Exception) -> tuple[str, str]:
    """Map a Telegram error to (state, human readable reason)."""
    text = str(error).lower()
    if isinstance(error, PartialSend):
        return PARTIAL, "The file was sent but the text could not be. Check the chat."
    if isinstance(error, Forbidden) or "not enough rights" in text or "have no rights" in text:
        return FAILED, "The bot can't post here. Make it an admin with 'Post messages'."
    if isinstance(error, BadRequest):
        if "chat not found" in text or "not a member" in text:
            return FAILED, "The bot can't see this chat any more. Add it again."
        if "wrong file" in text or "file_id" in text or "wrong remote file" in text:
            return FAILED, "The attached file expired. Attach it again."
        if "button" in text and "invalid" in text:
            return FAILED, "Telegram rejected one of the button links."
        if "too long" in text:
            return FAILED, "The text is too long for Telegram."
        return FAILED, "Telegram rejected this post. Edit it and try again."
    if isinstance(error, NetworkError):
        return UNCONFIRMED, "Delivery couldn't be confirmed. Check the chat before retrying."
    return FAILED, "Telegram could not send this post. Try again."


class Publisher:
    def __init__(self, bot: Bot, store: Any, invalidate: Any = None) -> None:
        self.bot = bot
        self.store = store
        self._invalidate = invalidate or (lambda user_id: None)
        self.jobs: dict[str, Job] = {}
        self.by_request: dict[tuple[int, str], str] = {}
        self.active: dict[int, str] = {}
        self._tasks: set[asyncio.Task] = set()
        self._admin_cache: dict[tuple[int, int], tuple[float, bool]] = {}

    def _gc(self) -> None:
        cutoff = time.monotonic() - JOB_TTL
        for job_id in [j for j, job in self.jobs.items() if job.done and job.created < cutoff]:
            job = self.jobs.pop(job_id)
            self.by_request.pop((job.user_id, job.request_id), None)

    def get(self, user_id: int, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        return job if job and job.user_id == user_id else None

    def latest(self, user_id: int) -> Job | None:
        mine = [j for j in self.jobs.values() if j.user_id == user_id]
        return max(mine, key=lambda j: j.created) if mine else None

    async def start(
        self, user_id: int, post: Post, chat_ids: list[int], request_id: str
    ) -> Job:
        self._gc()
        existing = self.by_request.get((user_id, request_id))
        if existing and existing in self.jobs:
            return self.jobs[existing]  # a retried request never posts twice
        running = self.jobs.get(self.active.get(user_id, ""))
        if running and not running.done:
            raise Busy
        owned = {c["chat_id"]: c for c in await self.store.list_user_chats(user_id)}
        order = [c for c in dict.fromkeys(chat_ids) if c in owned]
        if not order:
            raise NoTargets
        job = Job(
            id=uuid.uuid4().hex,
            user_id=user_id,
            post=post,
            request_id=request_id,
            results={
                cid: {
                    "chat_id": cid,
                    "title": owned[cid]["title"],
                    "type": owned[cid]["type"],
                    "status": QUEUED,
                    "error": None,
                    "url": None,
                }
                for cid in order
            },
        )
        self.jobs[job.id] = job
        self.by_request[(user_id, request_id)] = job.id
        self.active[user_id] = job.id
        task = asyncio.create_task(self._run(job, owned))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def wait(self, job: Job, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while not job.done and time.monotonic() < deadline:
            await asyncio.sleep(0.02)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run(self, job: Job, owned: dict[int, dict[str, Any]]) -> None:
        try:
            gate = asyncio.Semaphore(CONCURRENCY)
            await asyncio.gather(
                *(self._deliver(job, owned[cid], gate) for cid in list(job.results))
            )
            delivered = sum(r["status"] in (OK, PARTIAL) for r in job.results.values())
            if delivered:
                try:
                    await self.store.increment_posts(job.user_id, delivered)
                except StoreError as error:
                    logger.warning("Stats update failed (%s)", error)
        except asyncio.CancelledError:
            for row in job.results.values():
                if row["status"] not in FINAL:
                    row.update(status=FAILED, error="The server restarted. Try again.")
            raise
        except Exception:  # never leave a job hanging
            logger.exception("Publish job crashed")
            for row in job.results.values():
                if row["status"] not in FINAL:
                    row.update(status=FAILED, error="Something went wrong. Try again.")
        finally:
            job.done = True
            if self.active.get(job.user_id) == job.id:
                self.active.pop(job.user_id, None)

    async def _still_allowed(self, user_id: int, chat: dict[str, Any]) -> bool:
        key = (user_id, chat["chat_id"])
        cached = self._admin_cache.get(key)
        if cached and time.monotonic() - cached[0] < 60:
            return cached[1]
        try:
            member = await self.bot.get_chat_member(chat["chat_id"], user_id)
        except TelegramError:
            return True  # can't verify now; Telegram still enforces the bot's rights
        allowed = user_can_publish(chat["type"], member)
        self._admin_cache[key] = (time.monotonic(), allowed)
        return allowed

    async def _deliver(self, job: Job, chat: dict[str, Any], gate: asyncio.Semaphore) -> None:
        row = job.results[chat["chat_id"]]
        async with gate:
            row["status"] = SENDING
            if not await self._still_allowed(job.user_id, chat):
                try:
                    await self.store.unlink_chat(job.user_id, chat["chat_id"])
                    self._invalidate(job.user_id)
                except StoreError:
                    pass
                row.update(status=FAILED, error="You're no longer an admin of this chat.")
                return
            target, attempts = chat["chat_id"], 0
            while True:
                try:
                    message = await job.post.send(self.bot, target)
                    row.update(
                        status=OK,
                        url=message_url(chat, getattr(message, "message_id", None)),
                    )
                    return
                except RetryAfter as error:
                    delay = error.retry_after
                    seconds = (
                        delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay)
                    )
                    attempts += 1
                    if attempts > 2 or seconds > MAX_RETRY_WAIT:
                        row.update(
                            status=FAILED,
                            error=f"Telegram is busy. Retry in {int(seconds) + 1}s.",
                        )
                        return
                    row["error"] = f"Waiting {int(seconds) + 1}s (Telegram limit)..."
                    await asyncio.sleep(seconds + 0.2)
                    row["error"] = None
                except ChatMigrated as error:
                    attempts += 1
                    if attempts > 1:
                        row.update(status=FAILED, error="This group moved. Add it again.")
                        return
                    try:
                        await self.store.migrate_chat(target, error.new_chat_id)
                        self._invalidate(job.user_id)
                    except StoreError:
                        pass
                    target = error.new_chat_id
                except PartialSend as error:
                    state, reason = explain(error)
                    row.update(status=state, error=reason)
                    return
                except TelegramError as error:
                    state, reason = explain(error)
                    logger.warning(
                        "Delivery to %s failed (%s)", chat["chat_id"], type(error).__name__
                    )
                    row.update(status=state, error=reason)
                    if isinstance(error, Forbidden):
                        try:
                            await self.store.upsert_chat(chat["chat_id"], {"can_post": False})
                            self._invalidate(job.user_id)
                        except StoreError:
                            pass
                    return
                except ValueError:
                    row.update(status=FAILED, error="This post is not valid. Edit it and try again.")
                    return
