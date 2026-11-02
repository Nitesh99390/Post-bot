from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys

os.environ.setdefault("BOT_TOKEN", "123456789:TESTTOKENTESTTOKENTESTTOKEN")
os.environ.setdefault("WEBHOOK_URL", "https://example.onrender.com")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update  # noqa: E402
from telegram.ext import Application  # noqa: E402
from telegram.request import BaseRequest, RequestData  # noqa: E402

from bot import texts as T  # noqa: E402
from bot.config import ConfigError, Settings  # noqa: E402
from bot.handlers import register  # noqa: E402
from bot.post import normalize_url  # noqa: E402

CALLS: list[tuple[str, dict]] = []
USER = {"id": 42, "is_bot": False, "first_name": "Ravi"}
CHAT = {"id": 42, "type": "private", "first_name": "Ravi"}
_id = 0
REJECT_URLS: set[str] = set()


class FakeRequest(BaseRequest):
    async def initialize(self): ...

    async def shutdown(self): ...

    @property
    def read_timeout(self):
        return 5

    async def do_request(self, url, method, request_data: RequestData | None = None, **_):
        global _id
        name = url.rsplit("/", 1)[-1]
        params = request_data.json_parameters if request_data else {}
        params = {k: json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v for k, v in params.items()}
        _id += 1
        if name == "getMe":
            result = {"id": 1, "is_bot": True, "first_name": "Bot", "username": "test_bot"}
        else:
            CALLS.append((name, params))
            for row in (params.get("reply_markup") or {}).get("inline_keyboard", []):
                for b in row:
                    if b.get("url") in REJECT_URLS:
                        return 400, json.dumps({"ok": False, "description": "Bad Request: wrong HTTP URL"}).encode()
            result = {"message_id": _id, "date": 0, "chat": CHAT, "text": "x"}
        return 200, json.dumps({"ok": True, "result": result}).encode()


def msg(**kw):
    global _id
    _id += 1
    return {"update_id": _id, "message": {"message_id": _id, "date": 0, "chat": CHAT, "from": USER, **kw}}


async def send(app, **kw):
    CALLS.clear()
    await app.process_update(Update.de_json(msg(**kw), app.bot))
    return list(CALLS)


async def cmd(app, name):
    return await send(app, text=f"/{name}", entities=[{"type": "bot_command", "offset": 0, "length": len(name) + 1}])


def kb(call):
    return [[b["text"] for b in row] for row in (call[1].get("reply_markup") or {}).get("keyboard", [])]


def inline(call):
    return (call[1].get("reply_markup") or {}).get("inline_keyboard", [])


def last(calls):
    return calls[-1][1].get("text", "")


def test_config():
    s = Settings.from_env()
    assert s.use_webhook and s.webhook_url == "https://example.onrender.com/webhook"
    s.validate()
    try:
        dataclasses.replace(s, bot_token="nope").validate()
        raise AssertionError("invalid token accepted")
    except ConfigError:
        pass
    assert dataclasses.replace(s, base_url="http://x.com").use_webhook is False


def test_urls():
    assert normalize_url("@mychannel") == "https://t.me/mychannel"
    assert normalize_url("t.me/abc") == "https://t.me/abc"
    assert normalize_url("example.com/path?q=1") == "https://example.com/path?q=1"
    assert normalize_url("HTTP://Example.com") == "HTTP://Example.com"
    assert normalize_url("tg://resolve?domain=x") == "tg://resolve?domain=x"
    for bad in ("", "not a link", "nope", "ftp://x.com", "@ab", "http://", "localhost", "a..b"):
        assert normalize_url(bad) is None, bad


async def test_flow():
    app = Application.builder().token(os.environ["BOT_TOKEN"]).request(FakeRequest()).get_updates_request(FakeRequest()).build()
    register(app)
    await app.initialize()

    c = await cmd(app, "start")
    assert kb(c[-1]) == [[T.BTN_NEW, T.BTN_HELP]], c

    c = await send(app, text=T.BTN_NEW)
    assert "Step 1" in last(c) and kb(c[-1]) == [[T.BTN_CANCEL]]

    c = await send(app, animation={"file_id": "GIF1", "file_unique_id": "u", "width": 1, "height": 1, "duration": 1},
                   document={"file_id": "GIF1", "file_unique_id": "u"})
    assert c[0][0] == "sendAnimation" and c[0][1]["animation"] == "GIF1"
    assert kb(c[-1]) == [[T.BTN_TEXT, T.BTN_BUTTON], [T.BTN_UNDO, T.BTN_DONE], [T.BTN_CANCEL]], kb(c[-1])

    c = await send(app, text=T.BTN_TEXT)
    assert kb(c[-1]) == [[T.BTN_CANCEL]]
    c = await send(app, text="Hello <world> & friends")
    assert "Font style" in last(c)
    c = await send(app, text=T.STYLES["bold"][0])
    assert c[0][1]["caption"] == "<b>Hello &lt;world&gt; &amp; friends</b>", c[0]

    c = await send(app, text=T.BTN_BUTTON)
    await send(app, text="Join Channel")
    c = await send(app, text="not a link")
    assert "look like a link" in last(c)
    c = await send(app, text="@mychannel")
    assert kb(c[-1])[0] == ["🔴 Red", "🟢 Green", "🔵 Blue"]
    assert [b["style"] for b in c[-1][1]["reply_markup"]["keyboard"][0]] == ["danger", "success", "primary"]
    c = await send(app, text="🟢 Green")
    assert inline(c[0]) == [[{"text": "Join Channel", "url": "https://t.me/mychannel", "style": "success"}]]

    # Telegram rejects the link -> button removed, asked again
    REJECT_URLS.add("https://bad.example.com")
    await send(app, text=T.BTN_BUTTON)
    await send(app, text="Bad")
    await send(app, text="bad.example.com")
    c = await send(app, text="🔴 Red")
    assert "did not accept" in last(c)
    c = await send(app, text="good.example.com")
    c = await send(app, text="🔴 Red")
    assert [r[0]["style"] for r in inline(c[0])] == ["success", "danger"]

    # Undo removes the last button
    c = await send(app, text=T.BTN_UNDO)
    assert len(inline(c[-2])) == 1 and "Preview" in last(c)

    c = await send(app, text=T.BTN_DONE)
    assert c[0][0] == "sendAnimation" and "Published" in last(c)
    assert kb(c[-1]) == [[T.BTN_NEW, T.BTN_HELP]]

    # Emoji only
    await send(app, text=T.BTN_NEW)
    c = await send(app, text="😍🔥")
    assert c[0] == ("sendMessage", {**c[0][1]}) and c[0][1]["text"] == "😍🔥"

    # Sticker + text -> sticker, then message with text
    await send(app, text=T.BTN_NEW)
    c = await send(app, sticker={"file_id": "ST", "file_unique_id": "s", "width": 1, "height": 1,
                                 "is_animated": False, "is_video": False, "type": "regular"})
    assert c[0][0] == "sendSticker"
    await send(app, text=T.BTN_TEXT)
    await send(app, text="Hi")
    c = await send(app, text=T.STYLES["plain"][0])
    assert [x[0] for x in c] == ["sendSticker", "sendMessage", "sendMessage"]

    # Cancel from any step
    c = await send(app, text=T.BTN_CANCEL)
    assert "Cancelled" in last(c) and kb(c[-1]) == [[T.BTN_NEW, T.BTN_HELP]]

    # Long caption falls back to media + separate message
    await send(app, text=T.BTN_NEW)
    await send(app, photo=[{"file_id": "P1", "file_unique_id": "p", "width": 1, "height": 1}])
    await send(app, text=T.BTN_TEXT)
    await send(app, text="a" * 1500)
    c = await send(app, text=T.STYLES["quote"][0])
    assert [x[0] for x in c] == ["sendPhoto", "sendMessage", "sendMessage"] and "caption" not in c[0][1]

    # Undo back to empty returns to step 1
    await send(app, text=T.BTN_UNDO)
    c = await send(app, text=T.BTN_UNDO)
    assert "Step 1" in last(c)

    # Random text when idle / help
    await cmd(app, "start")
    c = await send(app, text="hello")
    assert T.BTN_NEW in last(c)
    c = await cmd(app, "help")
    assert "How it works" in last(c)

    # Group messages ignored
    CALLS.clear()
    group = {"id": -100, "type": "supergroup", "title": "G"}
    raw = {"update_id": 9999, "message": {"message_id": 9999, "date": 0, "chat": group, "from": USER, "text": "hi"}}
    await app.process_update(Update.de_json(raw, app.bot))
    assert CALLS == []

    await app.shutdown()


def main() -> None:
    test_config()
    test_urls()
    asyncio.run(test_flow())
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
