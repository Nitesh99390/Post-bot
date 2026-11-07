"""JSON API and static hosting for the Post Maker Mini App.

Every ``/api`` request carries Telegram's signed ``initData`` in the
``X-Init-Data`` header; the user id always comes from that verified data.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from aiohttp import web
from telegram import Bot, InputFile
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

from . import config
from .auth import AuthError, validate_init_data
from .chats import (
    CHAT_TYPES,
    chat_info,
    chat_type,
    member_can_post,
    parse_ref,
    register_chat,
)
from .post import (
    COLORS,
    MAX_BUTTON_TEXT,
    MAX_BUTTONS,
    Post,
    extract_media,
    normalize_url,
    plain_len,
    sanitize_html,
    utf16_len,
)
from .publisher import Busy, NoTargets, Publisher
from .store import MAX_CHATS, MAX_SAVED_POSTS, MemoryStore, StoreError, clean_name

logger = logging.getLogger(__name__)
WEBROOT = Path(__file__).resolve().parent.parent / "webapp"
USER_KEY = web.AppKey("user", dict)
SERVICES_KEY = web.AppKey("services", object)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def ok(**data: Any) -> web.Response:
    return web.json_response({"ok": True, **data}, headers={"Cache-Control": "no-store"})


class Services:
    """Everything the API needs, created once at startup."""

    def __init__(self, bot: Bot, store: Any, token: str) -> None:
        self.bot, self.store, self.token = bot, store, token
        self.publisher = Publisher(bot, store)
        self.drafts: dict[int, Post] = {}
        self.locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.touched: dict[int, float] = {}
        self.bot_username: str | None = None

    async def close(self) -> None:
        await self.publisher.close()

    # ----- draft ---------------------------------------------------------
    async def load_draft(self, user_id: int) -> Post:
        if user_id in self.drafts:
            return self.drafts[user_id]
        data = await self.store.load_session(user_id)
        post = Post.from_dict((data or {}).get("post")) or Post()
        return self.drafts.setdefault(user_id, post)

    async def save_draft(self, user_id: int, post: Post) -> None:
        self.drafts[user_id] = post  # memory first: a storage blip never loses edits
        if post.is_empty():
            await self.store.delete_session(user_id)
        else:
            await self.store.save_session(user_id, {"post": post.to_dict()})

    async def touch(self, user: dict[str, Any]) -> None:
        uid = user["id"]
        if time.monotonic() - self.touched.get(uid, -1e9) < 600:
            return
        self.touched[uid] = time.monotonic()
        info = {
            "first_name": str(user.get("first_name") or "")[:64],
            "last_name": str(user.get("last_name") or "")[:64] or None,
            "username": user.get("username"),
            "language_code": user.get("language_code"),
            "photo_url": user.get("photo_url"),
            "is_premium": bool(user.get("is_premium")),
        }
        try:
            await self.store.touch_user(uid, info)
        except StoreError as error:
            self.touched.pop(uid, None)
            logger.warning("touch_user failed (%s)", error)

    async def username(self) -> str:
        if not self.bot_username:
            self.bot_username = (await self.bot.get_me()).username or ""
        return self.bot_username


# ----- helpers ------------------------------------------------------------
def svc(request: web.Request) -> Services:
    return request.app[SERVICES_KEY]


def uid(request: web.Request) -> int:
    return request[USER_KEY]["id"]


async def body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "bad_json", "Invalid request.") from None
    if not isinstance(data, dict):
        raise ApiError(400, "bad_json", "Invalid request.")
    return data


def post_view(post: Post) -> dict[str, Any]:
    return {
        "text": post.text,
        "buttons": post.buttons,
        "link_preview": post.link_preview,
        "media_type": post.media_type,
        "media_name": post.media_name,
        "chars": plain_len(post.text.strip()),
        "splits": post.splits_text(),
        "empty": post.is_empty(),
    }


def profile_view(user: dict[str, Any], row: dict[str, Any], saved: int) -> dict[str, Any]:
    return {
        "id": user["id"],
        "first_name": user.get("first_name") or "",
        "last_name": user.get("last_name") or "",
        "username": user.get("username"),
        "photo_url": user.get("photo_url"),
        "is_premium": bool(user.get("is_premium")),
        "language_code": user.get("language_code"),
        "posts_created": int(row.get("posts_created") or 0),
        "deliveries": int(row.get("deliveries") or 0),
        "saved": saved,
    }


def parse_buttons(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise ApiError(422, "buttons", "Buttons are invalid.")
    if len(raw) > MAX_BUTTONS:
        raise ApiError(422, "buttons", f"Use up to {MAX_BUTTONS} buttons.")
    out = []
    for item in raw:
        if not isinstance(item, dict):
            raise ApiError(422, "buttons", "Buttons are invalid.")
        label = " ".join(str(item.get("text") or "").split())
        url = normalize_url(str(item.get("url") or ""))
        color = item.get("color") if item.get("color") in COLORS else "blue"
        if not label or utf16_len(label) > MAX_BUTTON_TEXT:
            raise ApiError(422, "buttons", f"Button names must be 1-{MAX_BUTTON_TEXT} characters.")
        if not url:
            raise ApiError(422, "buttons", f"'{label}' needs a valid link (https://… or @channel).")
        out.append({"text": label, "url": url, "color": color})
    return out


def friendly(error: Exception) -> ApiError:
    if isinstance(error, RetryAfter):
        return ApiError(429, "busy", "Telegram is busy. Try again in a few seconds.")
    if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
        return ApiError(503, "network", "Couldn't reach Telegram. Try again.")
    return ApiError(502, "telegram", "Telegram rejected the request.")


# ----- middleware ---------------------------------------------------------
@web.middleware
async def guard(request: web.Request, handler):
    path = request.path
    try:
        if path.startswith("/api/"):
            raw = request.headers.get("X-Init-Data", "")
            try:
                request[USER_KEY] = validate_init_data(
                    raw, config.BOT_TOKEN, config.INIT_DATA_MAX_AGE
                )
            except AuthError as error:
                code = "expired" if str(error) == "expired" else "auth"
                message = (
                    "This session expired. Close and reopen the app."
                    if code == "expired"
                    else "Open this app from Telegram."
                )
                raise ApiError(401, code, message) from None
        response = await handler(request)
    except ApiError as error:
        response = web.json_response(
            {"ok": False, "error": error.code, "message": error.message},
            status=error.status,
            headers={"Cache-Control": "no-store"},
        )
    except StoreError as error:
        logger.warning("Storage error on %s (%s)", path, error)
        response = web.json_response(
            {"ok": False, "error": "storage", "message": "Cloud sync is unavailable. Retrying…"},
            status=503,
            headers={"Cache-Control": "no-store", "Retry-After": "3"},
        )
    except web.HTTPException as error:
        if path.startswith("/api/"):
            response = web.json_response(
                {"ok": False, "error": "http", "message": error.reason}, status=error.status
            )
        else:
            raise
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Unhandled error on %s", path)
        response = web.json_response(
            {"ok": False, "error": "server", "message": "Something went wrong. Try again."},
            status=500,
        )
    if path.startswith(("/app", "/api")):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if path.startswith("/app"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' https://telegram.org; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
                "media-src 'self' blob:; connect-src 'self'; font-src 'self'; "
                "frame-ancestors https://web.telegram.org https://*.telegram.org "
                "https://*.t.me; base-uri 'none'; form-action 'none'",
            )
    return response


# ----- state --------------------------------------------------------------
async def get_state(request: web.Request) -> web.Response:
    s, user_id, user = svc(request), uid(request), request[USER_KEY]
    touch = asyncio.create_task(s.touch(user))
    results = await asyncio.gather(
        s.store.get_profile(user_id),
        s.store.list_user_chats(user_id),
        s.store.list_posts(user_id),
        s.load_draft(user_id),
        s.username(),
        return_exceptions=True,
    )
    await touch
    for result in results[:4]:
        if isinstance(result, StoreError):
            raise result
        if isinstance(result, Exception):
            raise result
    profile, chats, saved, draft, bot_name = results
    if isinstance(bot_name, Exception):
        bot_name = ""
    return ok(
        user=profile_view(user, profile, len(saved)),
        chats=chats,
        draft=post_view(draft),
        bot=bot_name,
        storage=s.store.name,
        limits={
            "text": 4000,
            "caption": 1024,
            "buttons": MAX_BUTTONS,
            "chats": MAX_CHATS,
            "saved": MAX_SAVED_POSTS,
            "upload_mb": config.MAX_UPLOAD // (1024 * 1024),
        },
        server_time=int(time.time()),
    )


# ----- draft --------------------------------------------------------------
async def put_draft(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    data = await body(request)
    text = data.get("text", "")
    if not isinstance(text, str):
        raise ApiError(422, "text", "Text is invalid.")
    clean = sanitize_html(text)
    buttons = parse_buttons(data.get("buttons", []))
    async with s.locks[user_id]:
        current = await s.load_draft(user_id)
        draft = Post(
            media_type=current.media_type,
            file_id=current.file_id,
            media_name=current.media_name,
            text=clean,
            buttons=buttons,
            link_preview=bool(data.get("link_preview", True)),
        )
        try:
            draft.validate()
        except ValueError as error:
            raise ApiError(422, "invalid", str(error)) from None
        await s.save_draft(user_id, draft)
    return ok(draft=post_view(draft))


async def delete_draft(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    async with s.locks[user_id]:
        await s.save_draft(user_id, Post())
    return ok(draft=post_view(Post()))


def media_kind(mime: str, size: int) -> str:
    if mime == "image/gif":
        return "animation"
    if mime in ("image/jpeg", "image/png", "image/webp"):
        return "photo" if size <= 10 * 1024 * 1024 else "document"
    if mime in ("video/mp4", "video/quicktime", "video/webm") and size <= 50 * 1024 * 1024:
        return "video" if mime == "video/mp4" else "document"
    if mime in ("audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a", "audio/aac"):
        return "audio"
    return "document"


async def upload_media(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    length = request.content_length
    if not length:
        raise ApiError(422, "empty", "That file is empty.")
    if length > config.MAX_UPLOAD:
        raise ApiError(413, "too_big", f"Files can be up to {config.MAX_UPLOAD // 1048576} MB.")
    chunks = bytearray()
    async for chunk in request.content.iter_chunked(65536):
        chunks += chunk
        if len(chunks) > config.MAX_UPLOAD:
            raise ApiError(413, "too_big", f"Files can be up to {config.MAX_UPLOAD // 1048576} MB.")
    if not chunks:
        raise ApiError(422, "empty", "That file is empty.")
    name = unquote(request.headers.get("X-File-Name", "file")).replace("/", "_")[:100] or "file"
    mime = request.headers.get("Content-Type", "").split(";")[0].strip().lower()
    kind = media_kind(mime, len(chunks))
    senders = {
        "photo": s.bot.send_photo,
        "animation": s.bot.send_animation,
        "video": s.bot.send_video,
        "audio": s.bot.send_audio,
        "document": s.bot.send_document,
    }
    async with s.locks[user_id]:
        message = None
        for attempt in (kind, "document") if kind != "document" else ("document",):
            try:
                message = await senders[attempt](
                    user_id, InputFile(bytes(chunks), filename=name), disable_notification=True
                )
                kind = attempt
                break
            except Forbidden:
                raise ApiError(
                    409, "no_chat", "Open the bot's chat once and press Start, then retry."
                ) from None
            except BadRequest as error:
                logger.info("Upload as %s rejected (%s)", attempt, error)
                continue  # e.g. odd photo size: retry as a plain file
            except TelegramError as error:
                raise friendly(error) from None
        if message is None:
            raise ApiError(422, "unsupported", "Telegram can't accept that file.")
        media_type, file_id = extract_media(message)
        if not file_id:
            raise ApiError(502, "telegram", "Telegram didn't return the file. Try again.")
        try:  # keep the user's chat tidy; the file id stays valid
            await s.bot.delete_message(user_id, message.message_id)
        except TelegramError:
            pass
        current = await s.load_draft(user_id)
        draft = Post(
            media_type=media_type,
            file_id=file_id,
            media_name=name,
            text=current.text,
            buttons=current.buttons,
            link_preview=current.link_preview,
        )
        await s.save_draft(user_id, draft)
    return ok(draft=post_view(draft))


async def delete_media(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    async with s.locks[user_id]:
        current = await s.load_draft(user_id)
        draft = Post(
            text=current.text, buttons=current.buttons, link_preview=current.link_preview
        )
        await s.save_draft(user_id, draft)
    return ok(draft=post_view(draft))


async def get_media(request: web.Request) -> web.Response:
    """Photo preview for the current draft (other media types show an icon)."""
    s, user_id = svc(request), uid(request)
    draft = await s.load_draft(user_id)
    if draft.media_type != "photo" or not draft.file_id:
        raise ApiError(404, "no_media", "No preview.")
    try:
        file = await s.bot.get_file(draft.file_id)
        data = await file.download_as_bytearray()
    except TelegramError as error:
        raise friendly(error) from None
    return web.Response(
        body=bytes(data),
        content_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=600"},
    )


# ----- chats --------------------------------------------------------------
async def list_chats(request: web.Request) -> web.Response:
    return ok(chats=await svc(request).store.list_user_chats(uid(request)))


async def add_chat(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    data = await body(request)
    ref = parse_ref(str(data.get("ref") or ""))
    if not ref:
        raise ApiError(422, "ref", "Enter @username, a t.me link or the -100… chat id.")
    try:
        chat = await s.bot.get_chat(ref)
    except RetryAfter as error:
        raise friendly(error) from None
    except BadRequest:
        raise ApiError(
            404,
            "not_found",
            "I can't find that chat. Add the bot as an admin first, then try again.",
        ) from None
    except TelegramError as error:
        raise friendly(error) from None
    kind = chat_type(chat)
    if kind not in CHAT_TYPES:
        raise ApiError(422, "type", "Only groups and channels can be added.")
    try:
        bot_member = await s.bot.get_chat_member(chat.id, s.bot.id)
    except TelegramError:
        bot_member = None
    if bot_member is None or not member_can_post(kind, bot_member):
        raise ApiError(
            409,
            "bot_not_admin",
            "Make the bot an admin with 'Post messages' in that chat, then try again.",
        )
    try:
        result = await register_chat(s.bot, s.store, user_id, chat, bot_member)
    except StoreError as error:
        if str(error) == "limit":
            raise ApiError(409, "limit", f"You can manage up to {MAX_CHATS} chats.") from None
        raise
    except TelegramError as error:
        raise friendly(error) from None
    if result == "not_admin":
        raise ApiError(
            403, "not_admin", "Only an admin who can post in that chat can add it here."
        )
    chats = await s.store.list_user_chats(user_id)
    return ok(result=result, chat_id=chat.id, chats=chats)


async def refresh_chats(request: web.Request) -> web.Response:
    """Re-read titles and the bot's permissions from Telegram."""
    s, user_id = svc(request), uid(request)
    chats = await s.store.list_user_chats(user_id)
    gate = asyncio.Semaphore(5)

    async def one(row: dict[str, Any]) -> None:
        async with gate:
            try:
                chat = await s.bot.get_chat(row["chat_id"])
                member = await s.bot.get_chat_member(chat.id, s.bot.id)
                can = member_can_post(chat_type(chat), member)
                await s.store.upsert_chat(chat.id, chat_info(chat, can))
            except StoreError:
                raise
            except TelegramError as error:
                if not isinstance(error, (RetryAfter, NetworkError)) or isinstance(error, BadRequest):
                    await s.store.upsert_chat(row["chat_id"], {"can_post": False})

    await asyncio.gather(*(one(r) for r in chats))
    return ok(chats=await s.store.list_user_chats(user_id))


def chat_id_from(request: web.Request, data: dict[str, Any] | None = None) -> int:
    raw = request.match_info.get("chat_id") if data is None else data.get("chat_id")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError(422, "chat_id", "Invalid chat.") from None
    return value


async def put_selection(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    data = await body(request)
    raw = data.get("chat_ids")
    if not isinstance(raw, list) or len(raw) > MAX_CHATS or any(type(c) is not int for c in raw):
        raise ApiError(422, "chat_ids", "Invalid selection.")
    owned = {c["chat_id"] for c in await s.store.list_user_chats(user_id)}
    await s.store.set_selection(user_id, [c for c in dict.fromkeys(raw) if c in owned])
    return ok(chats=await s.store.list_user_chats(user_id))


async def put_default(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    chat_id = chat_id_from(request, await body(request))
    if not await s.store.set_default(user_id, chat_id):
        raise ApiError(404, "not_found", "That chat isn't in your list.")
    return ok(chats=await s.store.list_user_chats(user_id))


async def remove_chat(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    await s.store.unlink_chat(user_id, chat_id_from(request))
    return ok(chats=await s.store.list_user_chats(user_id))


# ----- sending ------------------------------------------------------------
async def send_post(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    data = await body(request)
    request_id = str(data.get("request_id") or "")
    if not 8 <= len(request_id) <= 64:
        raise ApiError(422, "request_id", "Invalid request.")
    async with s.locks[user_id]:
        draft = await s.load_draft(user_id)
        if draft.is_empty():
            raise ApiError(422, "empty", "Write something or attach a file first.")
        try:
            draft.validate()
        except ValueError as error:
            raise ApiError(422, "invalid", str(error)) from None
        chats = await s.store.list_user_chats(user_id)
        raw = data.get("chat_ids")
        if raw is None:
            ids = [c["chat_id"] for c in chats if c["selected"]]
        elif isinstance(raw, list) and all(type(c) is int for c in raw):
            ids = raw
        else:
            raise ApiError(422, "chat_ids", "Invalid selection.")
        if not ids:
            raise ApiError(422, "no_targets", "Pick at least one group or channel.")
        try:
            job = await s.publisher.start(user_id, Post.from_dict(draft.to_dict()), ids, request_id)
        except Busy:
            raise ApiError(409, "busy", "Your previous send is still running.") from None
        except NoTargets:
            raise ApiError(422, "no_targets", "Those chats aren't in your list.") from None
    await s.publisher.wait(job, timeout=0.15)  # tiny sends finish within one round trip
    return ok(job=job.snapshot())


async def get_job(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    job = s.publisher.get(user_id, request.match_info["job_id"])
    if not job:
        raise ApiError(404, "not_found", "That send is no longer available.")
    return ok(job=job.snapshot())


async def get_active_job(request: web.Request) -> web.Response:
    job = svc(request).publisher.latest(uid(request))
    return ok(job=job.snapshot() if job else None)


# ----- saved posts --------------------------------------------------------
def saved_view(row: dict[str, Any]) -> dict[str, Any] | None:
    post = Post.from_dict(row.get("post"))
    if not post:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "updated_at": row.get("updated_at"),
        "media_type": post.media_type,
        "chars": plain_len(post.text.strip()),
        "buttons": len(post.buttons),
        "preview": post.plain_text()[:90],
    }


async def list_saved(request: web.Request) -> web.Response:
    rows = await svc(request).store.list_posts(uid(request))
    return ok(posts=[v for v in map(saved_view, rows) if v])


async def create_saved(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    data = await body(request)
    draft = await s.load_draft(user_id)
    if draft.is_empty():
        raise ApiError(422, "empty", "Nothing to save yet.")
    name = clean_name(str(data.get("name") or "")) or clean_name(draft.default_name())
    try:
        post_id, updated = await s.store.save_post(user_id, name, draft.to_dict())
    except StoreError as error:
        if str(error) == "limit":
            raise ApiError(
                409, "limit", f"You can keep {MAX_SAVED_POSTS} saved posts. Delete one first."
            ) from None
        raise
    rows = await s.store.list_posts(user_id)
    return ok(id=post_id, updated=updated, posts=[v for v in map(saved_view, rows) if v])


async def load_saved(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    try:
        post_id = int(request.match_info["post_id"])
    except ValueError:
        raise ApiError(404, "not_found", "Not found.") from None
    row = await s.store.get_post(user_id, post_id)
    post = Post.from_dict(row.get("post")) if row else None
    if not post:
        raise ApiError(404, "not_found", "That saved post doesn't exist.")
    async with s.locks[user_id]:
        await s.save_draft(user_id, post)
    return ok(draft=post_view(post))


async def delete_saved(request: web.Request) -> web.Response:
    s, user_id = svc(request), uid(request)
    try:
        post_id = int(request.match_info["post_id"])
    except ValueError:
        raise ApiError(404, "not_found", "Not found.") from None
    await s.store.delete_post(user_id, post_id)
    rows = await s.store.list_posts(user_id)
    return ok(posts=[v for v in map(saved_view, rows) if v])


# ----- static files -------------------------------------------------------
async def app_index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(WEBROOT / "index.html", headers={"Cache-Control": "no-cache"})


async def app_asset(request: web.Request) -> web.StreamResponse:
    root = WEBROOT.resolve()
    target = (root / request.match_info["path"]).resolve()
    if root not in target.parents or not target.is_file():
        raise web.HTTPNotFound()
    cache = "public, max-age=31536000, immutable" if target.suffix == ".woff2" else "no-cache"
    return web.FileResponse(target, headers={"Cache-Control": cache})


def add_routes(app: web.Application, services: Services) -> None:
    app[SERVICES_KEY] = services
    app.middlewares.append(guard)
    r = app.router
    r.add_get("/api/state", get_state)
    r.add_put("/api/draft", put_draft)
    r.add_delete("/api/draft", delete_draft)
    r.add_post("/api/media", upload_media)
    r.add_get("/api/media", get_media)
    r.add_delete("/api/media", delete_media)
    r.add_get("/api/chats", list_chats)
    r.add_post("/api/chats", add_chat)
    r.add_post("/api/chats/refresh", refresh_chats)
    r.add_put("/api/chats/selection", put_selection)
    r.add_put("/api/chats/default", put_default)
    r.add_delete("/api/chats/{chat_id}", remove_chat)
    r.add_post("/api/send", send_post)
    r.add_get("/api/send/active", get_active_job)
    r.add_get("/api/send/{job_id}", get_job)
    r.add_get("/api/posts", list_saved)
    r.add_post("/api/posts", create_saved)
    r.add_post("/api/posts/{post_id}/load", load_saved)
    r.add_delete("/api/posts/{post_id}", delete_saved)
    r.add_get("/app", lambda request: web.HTTPFound("/app/"))
    r.add_get("/app/", app_index)
    r.add_get("/app/{path:.+}", app_asset)
