"""End-to-end flow test with a fake Telegram API (no network, no real token).

Run:  BOT_TOKEN=1:test python -m tests.test_flow
"""
import asyncio
import json
import os
import sys

os.environ.setdefault("BOT_TOKEN", "123:TEST")
os.environ.setdefault("WEBHOOK_URL", "https://example.onrender.com")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update  # noqa: E402
from telegram.ext import Application  # noqa: E402
from telegram.request import BaseRequest, RequestData  # noqa: E402

from bot.handlers import register  # noqa: E402

CALLS: list[tuple[str, dict]] = []
USER = {"id": 42, "is_bot": False, "first_name": "Ravi"}
CHAT = {"id": 42, "type": "private", "first_name": "Ravi"}
_msg_id = 0


class FakeRequest(BaseRequest):
    async def initialize(self): ...
    async def shutdown(self): ...

    @property
    def read_timeout(self):
        return 5

    async def do_request(self, url, method, request_data: RequestData | None = None, **_):
        name = url.rsplit("/", 1)[-1]
        params = request_data.json_parameters if request_data else {}
        params = {k: json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v for k, v in params.items()}
        global _msg_id
        _msg_id += 1
        if name == "getMe":
            result = {"id": 1, "is_bot": True, "first_name": "Bot", "username": "test_bot"}
        else:
            CALLS.append((name, params))
            result = {"message_id": _msg_id, "date": 0, "chat": CHAT, "text": "x"}
        return 200, json.dumps({"ok": True, "result": result}).encode()


def msg(**kw):
    global _msg_id
    _msg_id += 1
    return {"update_id": _msg_id, "message": {"message_id": _msg_id, "date": 0, "chat": CHAT, "from": USER, **kw}}


async def send(app, **kw):
    CALLS.clear()
    await app.process_update(Update.de_json(msg(**kw), app.bot))
    return list(CALLS)


def kb_texts(call):
    rm = call[1].get("reply_markup") or {}
    return [[b["text"] for b in row] for row in rm.get("keyboard", [])]


def last_text(calls):
    return calls[-1][1].get("text", "")


async def main():
    app = Application.builder().token("123:TEST").request(FakeRequest()).get_updates_request(FakeRequest()).build()
    register(app)
    await app.initialize()

    c = await send(app, text="/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
    assert kb_texts(c[-1]) == [["✨ Create Post", "🎨 Mini App"]], c
    assert c[-1][1]["reply_markup"]["keyboard"][0][1]["web_app"]["url"] == "https://example.onrender.com/app"

    c = await send(app, text="✨ Create Post")
    assert "Step 1" in last_text(c) and c[-1][1]["reply_markup"] == {"remove_keyboard": True}

    # GIF
    c = await send(app, animation={"file_id": "GIF1", "file_unique_id": "u", "width": 1, "height": 1, "duration": 1},
                   document={"file_id": "GIF1", "file_unique_id": "u"})
    assert c[0][0] == "sendAnimation" and c[0][1]["animation"] == "GIF1", c
    assert kb_texts(c[-1]) == [["📝 Add Text", "🔘 Add Button"], ["✅ Done"]], c

    # Text
    c = await send(app, text="📝 Add Text")
    assert c[-1][1]["reply_markup"] == {"remove_keyboard": True}
    c = await send(app, text="Hello <world> & friends")
    assert c[0][0] == "sendAnimation" and c[0][1]["caption"] == "Hello &lt;world&gt; &amp; friends", c
    assert kb_texts(c[-1])[1] == ["✅ Done"]

    # Button
    c = await send(app, text="🔘 Add Button")
    assert c[-1][1]["reply_markup"] == {"remove_keyboard": True}
    await send(app, text="Join Channel")
    c = await send(app, text="not a link")
    assert "not a link" in last_text(c)
    c = await send(app, text="@mychannel")
    assert kb_texts(c[-1]) == [["🔴 Red", "🟢 Green", "🔵 Blue"]], c
    assert [b["style"] for b in c[-1][1]["reply_markup"]["keyboard"][0]] == ["danger", "success", "primary"]
    c = await send(app, text="🟢 Green")
    btn = c[0][1]["reply_markup"]["inline_keyboard"][0][0]
    assert btn == {"text": "Join Channel", "url": "https://t.me/mychannel", "style": "success"}, btn

    # Second button, red
    await send(app, text="🔘 Add Button")
    await send(app, text="Website")
    await send(app, text="example.com")
    c = await send(app, text="🔴 Red")
    rows = c[0][1]["reply_markup"]["inline_keyboard"]
    assert [r[0]["style"] for r in rows] == ["success", "danger"], rows

    # Done
    c = await send(app, text="✅ Done")
    assert c[0][0] == "sendAnimation" and "ready" in last_text(c)
    assert kb_texts(c[-1]) == [["✨ Create Post", "🎨 Mini App"]]

    # Emoji only + sticker path
    await send(app, text="✨ Create Post")
    c = await send(app, text="😍🔥")
    assert c[0][0] == "sendMessage" and c[0][1]["text"] == "😍🔥", c
    await send(app, text="✨ Create Post")
    c = await send(app, sticker={"file_id": "ST", "file_unique_id": "s", "width": 1, "height": 1,
                                 "is_animated": False, "is_video": False, "type": "regular"})
    assert c[0][0] == "sendSticker"
    await send(app, text="📝 Add Text")
    c = await send(app, text="Hi")
    assert [x[0] for x in c] == ["sendSticker", "sendMessage", "sendMessage"], c

    # Mini App data
    data = json.dumps({"emoji": "🎉", "text": "<b>x</b>", "buttons": [
        {"text": "Go", "url": "t.me/abc", "color": "red"}, {"text": "Bad", "url": "nope"}]})
    c = await send(app, web_app_data={"data": data, "button_text": "🎨 Mini App"})
    assert c[0][1]["text"] == "🎉\n\n&lt;b&gt;x&lt;/b&gt;", c
    assert c[0][1]["reply_markup"]["inline_keyboard"] == [[{"text": "Go", "url": "https://t.me/abc", "style": "danger"}]]
    c = await send(app, web_app_data={"data": "garbage", "button_text": "x"})
    assert "went wrong" in last_text(c)

    # Random text while the menu is open -> asked to pick a button
    c = await send(app, text="hello")
    assert "choose one of the buttons" in last_text(c), c

    # Random text when idle (after /start)
    await send(app, text="/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
    c = await send(app, text="hello")
    assert "Create Post" in last_text(c)

    # Very long text with a photo -> photo first, then text message with buttons
    await send(app, text="✨ Create Post")
    await send(app, photo=[{"file_id": "P1", "file_unique_id": "p", "width": 1, "height": 1}])
    await send(app, text="📝 Add Text")
    c = await send(app, text="a" * 1500)
    assert [x[0] for x in c] == ["sendPhoto", "sendMessage", "sendMessage"], c
    assert "caption" not in c[0][1]

    await app.shutdown()
    print("✅ ALL FLOW TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
