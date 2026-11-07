"""Run the Mini App locally with a fake Telegram bot and in-memory storage.

    python3 tools/devserver.py [port]

Prints a signed ``initData`` string for a demo user. Development only: no
real bot token, network access or Supabase is needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp import web  # noqa: E402
from telegram.error import Forbidden  # noqa: E402

from bot import config  # noqa: E402
from bot.api import Services, add_routes  # noqa: E402
from bot.auth import sign  # noqa: E402
from bot.store import MemoryStore  # noqa: E402

TOKEN = "123456:DEV-TOKEN-NOT-REAL"
USER = {"id": 4242, "first_name": "Aarav", "last_name": "Sharma", "username": "aarav_dev",
        "language_code": "en", "is_premium": True}
CHATS = {
    -1001000000001: ("channel", "Daily Deals", "dailydeals", True),
    -1001000000002: ("supergroup", "Design Team", None, True),
    -1001000000003: ("channel", "Crypto Alerts", "cryptoalerts", True),
    -1001000000004: ("group", "Family", None, False),
}
FAIL = {-1001000000003}


def init_data(user: dict = USER, token: str = TOKEN, age: int = 0) -> str:
    fields = {"auth_date": str(int(time.time()) - age), "query_id": "AAHdev", "user": json.dumps(user, separators=(",", ":"))}
    fields["hash"] = sign(fields, token)
    return urlencode(fields)


class FakeBot:
    id = 777
    username = "postmaker_dev_bot"

    def __init__(self) -> None:
        self.sent: list[tuple] = []
        self._n = 100

    async def get_me(self):
        return SimpleNamespace(username=self.username, id=self.id)

    async def get_chat(self, ref):
        for cid, (kind, title, uname, _) in CHATS.items():
            if ref in (cid, f"@{uname}"):
                return SimpleNamespace(id=cid, type=kind, title=title, username=uname)
        from telegram.error import BadRequest
        raise BadRequest("Chat not found")

    async def get_chat_member(self, chat_id, user_id):
        ok = CHATS.get(chat_id, ("", "", None, False))[3]
        if user_id == self.id:
            return SimpleNamespace(status="administrator" if ok else "member", can_post_messages=ok)
        return SimpleNamespace(status="creator", can_post_messages=True)

    async def _send(self, chat_id, *args, **kwargs):
        await asyncio.sleep(0.35)
        if chat_id in FAIL:
            raise Forbidden("Forbidden: bot is not a member of the channel chat")
        self._n += 1
        self.sent.append((chat_id, args, kwargs))
        return SimpleNamespace(message_id=self._n)

    send_message = send_photo = send_video = send_animation = send_audio = send_document = _send
    send_voice = send_sticker = send_video_note = _send

    async def delete_message(self, *a, **k):
        return True


def make_app() -> tuple[web.Application, Services]:
    config.BOT_TOKEN = TOKEN  # the API validates initData against this token
    store = MemoryStore()
    bot = FakeBot()
    services = Services(bot, store, TOKEN)  # type: ignore[arg-type]
    app = web.Application(client_max_size=40 * 1024 * 1024)

    async def seed(_app):
        for cid, (kind, title, uname, can) in CHATS.items():
            await store.upsert_chat(cid, {"type": kind, "title": title, "username": uname, "can_post": can})
            await store.link_chat(USER["id"], cid)

    app.on_startup.append(seed)
    add_routes(app, services)
    return app, services


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    app, _ = make_app()
    print("initData:", init_data(), flush=True)
    web.run_app(app, host="0.0.0.0", port=port, access_log=None)
