"""Offline tests for the Mini App backend: auth, sanitizer, chats, publisher, API."""

import asyncio
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from aiohttp.test_utils import TestClient, TestServer
from telegram.error import BadRequest, ChatMigrated, Forbidden, NetworkError, RetryAfter

from bot import config
from bot.api import Services, add_routes
from bot.auth import AuthError, sign, validate_init_data
from bot.chats import member_can_post, parse_ref, user_can_publish
from bot.post import PartialSend, Post, sanitize_html
from bot.publisher import Busy, Publisher
from bot.store import MAX_CHATS, MemoryStore, StoreError

TOKEN = "123456:TEST-TOKEN"
USER = {"id": 7, "first_name": "Ravi", "last_name": "K", "username": "ravi", "is_premium": True}


def init_data(user=USER, token=TOKEN, age=0, tamper=False):
    fields = {"auth_date": str(int(time.time()) - age), "query_id": "AA", "user": json.dumps(user)}
    fields["hash"] = sign(fields, token)
    if tamper:
        fields["user"] = json.dumps({**user, "id": 999})
    return urlencode(fields)


class AuthTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_init_data(init_data(), TOKEN, 3600)["id"], 7)

    def test_rejects_forgery_expiry_and_garbage(self):
        for raw, token in (
            (init_data(tamper=True), TOKEN),
            (init_data(), "999:OTHER"),
            (init_data(age=7200), TOKEN),
            ("", TOKEN),
            ("hash=abc", TOKEN),
            ("a=1&a=2&hash=x", TOKEN),
            (init_data(user={"id": "7"}), TOKEN),
            (init_data(user={"id": -1}), TOKEN),
        ):
            with self.subTest(raw=raw[:30]), self.assertRaises(AuthError):
                validate_init_data(raw, token, 3600)

    def test_signature_field_is_part_of_the_check_string(self):
        fields = {"auth_date": str(int(time.time())), "user": json.dumps(USER), "signature": "sig"}
        fields["hash"] = sign(fields, TOKEN)
        self.assertEqual(validate_init_data(urlencode(fields), TOKEN, 60)["id"], 7)


class SanitizerTests(unittest.TestCase):
    def test_keeps_allowed_and_strips_dangerous(self):
        self.assertEqual(sanitize_html("<b>a</b> <i>b</i>"), "<b>a</b> <i>b</i>")
        self.assertEqual(sanitize_html("<script>x</script>hi"), "xhi")
        self.assertNotIn("javascript", sanitize_html('<a href="javascript:alert(1)">x</a>'))
        self.assertIn('<a href="https://a.com">', sanitize_html('<a href="https://a.com">x</a>'))
        self.assertEqual(sanitize_html("1 < 2 & 3"), "1 &lt; 2 &amp; 3")

    def test_unbalanced_and_empty_tags_become_valid(self):
        self.assertEqual(sanitize_html("<b>open"), "<b>open</b>")
        self.assertEqual(sanitize_html("<b></b>x"), "x")
        self.assertEqual(sanitize_html("</i>x"), "x")

    def test_no_markup_inside_code(self):
        out = sanitize_html("<code><b>x</b></code>")
        self.assertNotIn("<b>", out)


class ChatRuleTests(unittest.TestCase):
    def test_permissions(self):
        m = lambda **k: SimpleNamespace(**k)  # noqa: E731
        self.assertTrue(user_can_publish("channel", m(status="creator")))
        self.assertFalse(user_can_publish("channel", m(status="administrator", can_post_messages=False)))
        self.assertTrue(user_can_publish("group", m(status="administrator")))
        self.assertFalse(user_can_publish("group", m(status="member")))
        self.assertTrue(member_can_post("group", m(status="member")))
        self.assertFalse(member_can_post("channel", m(status="member")))
        self.assertFalse(member_can_post("channel", m(status="left")))

    def test_parse_ref(self):
        for raw, want in (
            ("@news_chan", "@news_chan"),
            ("https://t.me/news_chan", "@news_chan"),
            ("t.me/news_chan/12", "@news_chan"),
            ("-1001234567890", "-1001234567890"),
            ("hi", None),
            ("https://example.com/x", None),
            ("", None),
        ):
            self.assertEqual(parse_ref(raw), want, raw)


class ChatStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.s = MemoryStore()
        for cid in (-1, -2, -3):
            await self.s.upsert_chat(cid, {"type": "group", "title": f"G{-cid}", "can_post": True})

    async def test_first_chat_is_default_and_selected(self):
        self.assertTrue(await self.s.link_chat(1, -1))
        self.assertFalse(await self.s.link_chat(1, -1))
        await self.s.link_chat(1, -2)
        rows = await self.s.list_user_chats(1)
        self.assertEqual([(r["chat_id"], r["is_default"], r["selected"]) for r in rows], [(-1, True, True), (-2, False, False)])

    async def test_exactly_one_default_and_promotion(self):
        for c in (-1, -2, -3):
            await self.s.link_chat(1, c)
        self.assertTrue(await self.s.set_default(1, -3))
        self.assertFalse(await self.s.set_default(1, -99))
        self.assertEqual([r["chat_id"] for r in await self.s.list_user_chats(1) if r["is_default"]], [-3])
        await self.s.unlink_chat(1, -3)
        rows = await self.s.list_user_chats(1)
        self.assertEqual(sum(r["is_default"] for r in rows), 1)

    async def test_selection_is_per_user(self):
        await self.s.link_chat(1, -1); await self.s.link_chat(1, -2); await self.s.link_chat(2, -1)
        await self.s.set_selection(1, [-1, -2])
        self.assertEqual(sum(r["selected"] for r in await self.s.list_user_chats(1)), 2)
        await self.s.set_selection(1, [])
        self.assertEqual(sum(r["selected"] for r in await self.s.list_user_chats(1)), 0)
        self.assertTrue((await self.s.list_user_chats(2))[0]["selected"])

    async def test_drop_migrate_and_limit(self):
        await self.s.link_chat(1, -1); await self.s.link_chat(2, -1)
        await self.s.migrate_chat(-1, -100)
        self.assertEqual([r["chat_id"] for r in await self.s.list_user_chats(1)], [-100])
        await self.s.drop_chat(-100)
        self.assertEqual(await self.s.list_user_chats(1), [])
        self.assertEqual(await self.s.list_user_chats(2), [])
        for i in range(MAX_CHATS):
            await self.s.upsert_chat(1000 + i, {"title": "x"}); await self.s.link_chat(5, 1000 + i)
        await self.s.upsert_chat(5000, {"title": "x"})
        with self.assertRaises(StoreError):
            await self.s.link_chat(5, 5000)


class FakeBot:
    id = 777
    username = "pm_bot"

    def __init__(self):
        self.sent = []
        self.fail = {}      # chat_id -> list of exceptions to raise (consumed in order)
        self.gate = None    # optional asyncio.Event to hold sends
        self.members = {}   # (chat, user) -> status namespace
        self.chats = {}
        self.deleted = []

    async def get_me(self):
        return SimpleNamespace(username=self.username, id=self.id)

    async def get_chat(self, ref):
        if ref in self.chats:
            return self.chats[ref]
        raise BadRequest("Chat not found")

    async def get_chat_member(self, chat_id, user_id):
        return self.members.get((chat_id, user_id), SimpleNamespace(status="creator", can_post_messages=True))

    async def _send(self, chat_id, *a, **k):
        if self.gate:
            await self.gate.wait()
        errs = self.fail.get(chat_id)
        if errs:
            raise errs.pop(0)
        self.sent.append((chat_id, a, k))
        return SimpleNamespace(message_id=len(self.sent))

    send_message = send_photo = send_document = send_video = send_animation = send_audio = _send

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


async def seeded_store(user=7, chats=((-1001, "channel", "Alpha"), (-1002, "supergroup", "Beta"), (-1003, "group", "Gamma"))):
    store = MemoryStore()
    for cid, kind, title in chats:
        await store.upsert_chat(cid, {"type": kind, "title": title, "username": None, "can_post": True})
        await store.link_chat(user, cid)
    return store


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = FakeBot()
        self.store = await seeded_store()
        self.pub = Publisher(self.bot, self.store)
        self.post = Post(text="<b>Hello</b>")

    async def asyncTearDown(self):
        await self.pub.close()

    async def run_job(self, ids=(-1001, -1002, -1003), rid="req-00000001"):
        job = await self.pub.start(7, self.post, list(ids), rid)
        await self.pub.wait(job, timeout=5)
        return job

    async def test_fan_out_success_and_stats(self):
        job = await self.run_job()
        snap = job.snapshot()
        self.assertTrue(snap["done"])
        self.assertEqual((snap["ok"], snap["failed"], snap["total"]), (3, 0, 3))
        self.assertEqual({c for c, *_ in self.bot.sent}, {-1001, -1002, -1003})
        profile = await self.store.get_profile(7)
        self.assertEqual((profile["posts_created"], profile["deliveries"]), (1, 3))

    async def test_one_failure_does_not_stop_others(self):
        self.bot.fail[-1002] = [Forbidden("Forbidden: bot was kicked")]
        snap = (await self.run_job()).snapshot()
        self.assertEqual((snap["ok"], snap["failed"]), (2, 1))
        bad = next(r for r in snap["results"] if r["chat_id"] == -1002)
        self.assertEqual(bad["status"], "failed")
        self.assertIn("admin", bad["error"].lower())
        chats = {c["chat_id"]: c for c in await self.store.list_user_chats(7)}
        self.assertFalse(chats[-1002]["can_post"])

    async def test_retry_after_is_waited_and_retried(self):
        self.bot.fail[-1001] = [RetryAfter(0.05)]
        snap = (await self.run_job()).snapshot()
        self.assertEqual(snap["ok"], 3)

    async def test_network_error_is_unconfirmed_not_retried(self):
        self.bot.fail[-1001] = [NetworkError("boom")]
        snap = (await self.run_job()).snapshot()
        self.assertEqual((snap["ok"], snap["unconfirmed"]), (2, 1))
        self.assertEqual(sum(c == -1001 for c, *_ in self.bot.sent), 0)  # no blind resend

    async def test_chat_migration_updates_store(self):
        self.bot.fail[-1003] = [ChatMigrated(-1009)]
        snap = (await self.run_job()).snapshot()
        self.assertEqual(snap["ok"], 3)
        self.assertIn(-1009, {c["chat_id"] for c in await self.store.list_user_chats(7)})

    async def test_partial_send_is_reported(self):
        async def partial(*a, **k):
            raise PartialSend(BadRequest("text failed"))
        self.post = Post(text="x")
        with patch.object(Post, "send", side_effect=partial):
            snap = (await self.run_job(ids=[-1001])).snapshot()
        self.assertEqual(snap["results"][0]["status"], "partial")

    async def test_idempotent_request_and_busy(self):
        self.bot.gate = asyncio.Event()
        first = await self.pub.start(7, self.post, [-1001], "req-AAAAAAAA")
        again = await self.pub.start(7, self.post, [-1001], "req-AAAAAAAA")
        self.assertIs(first, again)
        with self.assertRaises(Busy):
            await self.pub.start(7, self.post, [-1002], "req-BBBBBBBB")
        self.bot.gate.set()
        await self.pub.wait(first, timeout=5)
        self.assertEqual(len(self.bot.sent), 1)  # sent once despite two requests
        self.assertIsNotNone(self.pub.get(7, first.id))
        self.assertIsNone(self.pub.get(8, first.id))  # other users can't read it

    async def test_unlinks_chat_when_user_lost_admin(self):
        self.bot.members[(-1002, 7)] = SimpleNamespace(status="member")
        snap = (await self.run_job()).snapshot()
        self.assertEqual((snap["ok"], snap["failed"]), (2, 1))
        self.assertNotIn(-1002, {c["chat_id"] for c in await self.store.list_user_chats(7)})

    async def test_only_owned_chats_are_targeted(self):
        job = await self.run_job(ids=[-1001, -4444])
        self.assertEqual(job.snapshot()["total"], 1)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patch = patch.object(config, "BOT_TOKEN", TOKEN)
        self.patch.start()
        self.bot = FakeBot()
        self.store = await seeded_store()
        self.services = Services(self.bot, self.store, TOKEN)
        from aiohttp import web
        app = web.Application(client_max_size=40 * 1024 * 1024)
        add_routes(app, self.services)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.h = {"X-Init-Data": init_data()}

    async def asyncTearDown(self):
        await self.client.close()
        await self.services.close()
        self.patch.stop()

    async def call(self, method, path, body=None, headers=None, **kw):
        r = await self.client.request(method, path, json=body, headers=self.h if headers is None else headers, **kw)
        return r.status, await r.json()

    async def test_auth_required_and_expired(self):
        status, data = await self.call("GET", "/api/state", headers={})
        self.assertEqual((status, data["error"]), (401, "auth"))
        status, data = await self.call("GET", "/api/state", headers={"X-Init-Data": init_data(age=10 * 24 * 3600)})
        self.assertEqual((status, data["error"]), (401, "expired"))

    async def test_state_has_profile_chats_draft(self):
        status, data = await self.call("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["first_name"], "Ravi")
        self.assertTrue(data["user"]["is_premium"])
        self.assertEqual(len(data["chats"]), 3)
        self.assertEqual(data["bot"], "pm_bot")
        self.assertTrue(data["draft"]["empty"])

    async def test_draft_roundtrip_sanitizes_and_validates(self):
        status, data = await self.call("PUT", "/api/draft", {
            "text": "<b>hi</b><script>x</script>", "link_preview": False,
            "buttons": [{"text": "Go", "url": "example.com", "color": "green"}]})
        self.assertEqual(status, 200)
        _, state = await self.call("GET", "/api/state")
        self.assertNotIn("script", state["draft"]["text"])
        self.assertEqual(state["draft"]["buttons"][0]["url"], "https://example.com")
        self.assertFalse(state["draft"]["link_preview"])
        status, data = await self.call("PUT", "/api/draft", {"text": "x", "buttons": [{"text": "A", "url": "javascript:1", "color": "blue"}]})
        self.assertEqual((status, data["error"]), (422, "buttons"))
        _, state2 = await self.call("GET", "/api/state")
        self.assertEqual(state2["draft"]["text"], state["draft"]["text"])  # bad save changed nothing

    async def test_users_are_isolated(self):
        await self.call("PUT", "/api/draft", {"text": "mine", "buttons": []})
        other = {"X-Init-Data": init_data(user={"id": 8, "first_name": "Other"})}
        _, state = await self.call("GET", "/api/state", headers=other)
        self.assertEqual(state["draft"]["text"], "")
        self.assertEqual(state["chats"], [])

    async def test_selection_default_remove(self):
        status, data = await self.call("PUT", "/api/chats/selection", {"chat_ids": [-1001, -1002, -999]})
        self.assertEqual(status, 200)
        self.assertEqual({c["chat_id"] for c in data["chats"] if c["selected"]}, {-1001, -1002})
        status, data = await self.call("PUT", "/api/chats/default", {"chat_id": -1003})
        self.assertEqual([c["chat_id"] for c in data["chats"] if c["is_default"]], [-1003])
        status, data = await self.call("PUT", "/api/chats/default", {"chat_id": -5})
        self.assertEqual(status, 404)
        status, data = await self.call("PUT", "/api/chats/selection", {"chat_ids": "x"})
        self.assertEqual(status, 422)
        status, data = await self.call("DELETE", "/api/chats/-1003")
        self.assertEqual(len(data["chats"]), 2)
        self.assertEqual(sum(c["is_default"] for c in data["chats"]), 1)

    async def test_add_chat_by_username(self):
        self.bot.chats["@newchan"] = SimpleNamespace(id=-1004, type="channel", title="New", username="newchan")
        self.bot.members[(-1004, self.bot.id)] = SimpleNamespace(status="administrator", can_post_messages=True)
        status, data = await self.call("POST", "/api/chats", {"ref": "t.me/newchan"})
        self.assertEqual((status, data["result"]), (200, "linked"))
        status, data = await self.call("POST", "/api/chats", {"ref": "@newchan"})
        self.assertEqual(data["result"], "exists")
        self.bot.members[(-1004, self.bot.id)] = SimpleNamespace(status="member")
        self.bot.chats["@nope_chan"] = SimpleNamespace(id=-1005, type="channel", title="N", username="nope_chan")
        self.bot.members[(-1005, self.bot.id)] = SimpleNamespace(status="member")
        status, data = await self.call("POST", "/api/chats", {"ref": "@nope_chan"})
        self.assertEqual((status, data["error"]), (409, "bot_not_admin"))
        status, data = await self.call("POST", "/api/chats", {"ref": "@missing_x"})
        self.assertEqual(status, 404)
        status, data = await self.call("POST", "/api/chats", {"ref": "???"})
        self.assertEqual(status, 422)

    async def test_add_chat_requires_user_admin(self):
        self.bot.chats["@theirs"] = SimpleNamespace(id=-1006, type="supergroup", title="T", username="theirs")
        self.bot.members[(-1006, self.bot.id)] = SimpleNamespace(status="administrator", can_post_messages=True)
        self.bot.members[(-1006, 7)] = SimpleNamespace(status="member")
        status, data = await self.call("POST", "/api/chats", {"ref": "@theirs"})
        self.assertEqual((status, data["error"]), (403, "not_admin"))

    async def send_and_wait(self, body):
        status, data = await self.call("POST", "/api/send", body)
        if status != 200:
            return status, data
        for _ in range(100):
            _, poll = await self.call("GET", f"/api/send/{data['job']['id']}")
            if poll["job"]["done"]:
                return 200, poll
            await asyncio.sleep(0.03)
        self.fail("job never finished")

    async def test_send_flow(self):
        status, data = await self.call("POST", "/api/send", {"request_id": "r-12345678"})
        self.assertEqual((status, data["error"]), (422, "empty"))
        await self.call("PUT", "/api/draft", {"text": "Hello", "buttons": [{"text": "A", "url": "a.com", "color": "red"}]})
        status, data = await self.call("POST", "/api/send", {"request_id": "x"})
        self.assertEqual(data["error"], "request_id")
        await self.call("PUT", "/api/chats/selection", {"chat_ids": []})
        status, data = await self.call("POST", "/api/send", {"request_id": "r-12345678"})
        self.assertEqual((status, data["error"]), (422, "no_targets"))
        await self.call("PUT", "/api/chats/selection", {"chat_ids": [-1001, -1002]})
        status, poll = await self.send_and_wait({"request_id": "r-87654321"})  # uses selection
        self.assertEqual((poll["job"]["ok"], poll["job"]["total"]), (2, 2))
        self.assertEqual(len(self.bot.sent), 2)
        markup = self.bot.sent[0][2]["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].text, "A")
        _, state = await self.call("GET", "/api/state")
        self.assertEqual((state["user"]["posts_created"], state["user"]["deliveries"]), (1, 2))
        self.assertEqual(state["draft"]["text"], "Hello")  # draft survives a send

    async def test_send_retry_with_same_request_id_does_not_duplicate(self):
        await self.call("PUT", "/api/draft", {"text": "Hello", "buttons": []})
        body = {"request_id": "r-same-0001", "chat_ids": [-1001]}
        _, a = await self.call("POST", "/api/send", body)
        await asyncio.sleep(0.2)
        _, b = await self.call("POST", "/api/send", body)
        self.assertEqual(a["job"]["id"], b["job"]["id"])
        self.assertEqual(len(self.bot.sent), 1)

    async def test_busy_and_active_job(self):
        await self.call("PUT", "/api/draft", {"text": "Hello", "buttons": []})
        self.bot.gate = asyncio.Event()
        _, a = await self.call("POST", "/api/send", {"request_id": "r-busy-0001", "chat_ids": [-1001]})
        self.assertFalse(a["job"]["done"])
        status, b = await self.call("POST", "/api/send", {"request_id": "r-busy-0002", "chat_ids": [-1002]})
        self.assertEqual((status, b["error"]), (409, "busy"))
        _, act = await self.call("GET", "/api/send/active")
        self.assertEqual(act["job"]["id"], a["job"]["id"])
        self.bot.gate.set()
        await asyncio.sleep(0.2)
        status, _ = await self.call("GET", "/api/send/nonexistent")
        self.assertEqual(status, 404)

    async def test_saved_posts_cycle(self):
        status, data = await self.call("POST", "/api/posts", {"name": "x"})
        self.assertEqual((status, data["error"]), (422, "empty"))
        await self.call("PUT", "/api/draft", {"text": "Promo <b>now</b>", "buttons": []})
        status, data = await self.call("POST", "/api/posts", {"name": "Promo"})
        self.assertEqual(len(data["posts"]), 1)
        pid = data["id"]
        status, data = await self.call("POST", "/api/posts", {"name": "promo"})
        self.assertTrue(data["updated"])
        self.assertEqual(len(data["posts"]), 1)
        await self.call("DELETE", "/api/draft")
        _, state = await self.call("GET", "/api/state")
        self.assertTrue(state["draft"]["empty"])
        status, data = await self.call("POST", f"/api/posts/{pid}/load", {})
        self.assertIn("Promo", data["draft"]["text"])
        status, data = await self.call("POST", "/api/posts/9999/load", {})
        self.assertEqual(status, 404)
        status, data = await self.call("DELETE", f"/api/posts/{pid}")
        self.assertEqual(data["posts"], [])

    async def test_media_upload_and_clear(self):
        async def send_photo(chat_id, photo, **k):
            return SimpleNamespace(message_id=5, photo=[SimpleNamespace(file_id="FILE1")],
                                   **{m: None for m in ("animation", "video", "audio", "voice", "document", "sticker", "video_note")})
        self.bot.send_photo = send_photo
        r = await self.client.post("/api/media", data=b"\x89PNG" + b"0" * 100, headers={**self.h, "Content-Type": "image/png", "X-File-Name": "pic.png"})
        data = await r.json()
        self.assertEqual((r.status, data["draft"]["media_type"], data["draft"]["media_name"]), (200, "photo", "pic.png"))
        self.assertEqual(self.bot.deleted, [(7, 5)])
        r = await self.client.post("/api/media", data=b"", headers={**self.h, "Content-Type": "image/png"})
        self.assertEqual(r.status, 422)
        status, data = await self.call("DELETE", "/api/media")
        self.assertEqual(status, 200)
        _, state = await self.call("GET", "/api/state")
        self.assertIsNone(state["draft"]["media_type"])

    async def test_static_app_and_security_headers(self):
        r = await self.client.get("/app/")
        self.assertEqual(r.status, 200)
        self.assertIn("frame-ancestors", r.headers["Content-Security-Policy"])
        self.assertEqual((await self.client.get("/app/style.css")).status, 200)
        self.assertEqual((await self.client.get("/app/../bot/config.py")).status, 404)
        self.assertEqual((await self.client.get("/app/%2e%2e/main.py")).status, 404)
        self.assertEqual((await self.client.get("/app/nope.js")).status, 404)


class BotHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_my_chat_member_links_and_drops(self):
        from bot import handlers as h

        store = await seeded_store(chats=())
        bot = FakeBot()
        chat = SimpleNamespace(id=-1100, type="supergroup", title="Team", username=None)
        context = SimpleNamespace(bot=bot, bot_data={"store": store})

        def update(status):
            return SimpleNamespace(my_chat_member=SimpleNamespace(
                chat=chat, from_user=SimpleNamespace(id=7), new_chat_member=SimpleNamespace(status=status, can_post_messages=True)))

        await h.on_my_chat_member(update("administrator"), context)
        rows = await store.list_user_chats(7)
        self.assertEqual([(r["chat_id"], r["is_default"], r["can_post"]) for r in rows], [(-1100, True, True)])
        await h.on_my_chat_member(update("administrator"), context)  # idempotent
        self.assertEqual(len(await store.list_user_chats(7)), 1)
        await h.on_my_chat_member(update("kicked"), context)
        self.assertEqual(await store.list_user_chats(7), [])

    async def test_private_chat_updates_are_ignored(self):
        from bot import handlers as h

        store = await seeded_store(chats=())
        private = SimpleNamespace(id=7, type="private", title=None, username="x")
        update = SimpleNamespace(my_chat_member=SimpleNamespace(chat=private, from_user=SimpleNamespace(id=7), new_chat_member=SimpleNamespace(status="member")))
        await h.on_my_chat_member(update, SimpleNamespace(bot=FakeBot(), bot_data={"store": store}))
        self.assertEqual(await store.list_user_chats(7), [])

    def test_commands_are_minimal(self):
        from bot import handlers as h
        self.assertEqual([c for c, _ in h.COMMANDS], ["start"])


class WebhookChatMemberTests(unittest.IsolatedAsyncioTestCase):
    async def test_my_chat_member_payload_is_queued_and_bad_one_rejected(self):
        from aiohttp.test_utils import make_mocked_request
        from telegram.ext import Application
        from unittest.mock import AsyncMock, MagicMock

        from main import build_web_app

        application = SimpleNamespace(bot=Application.builder().token(TOKEN).build().bot, running=True, update_queue=asyncio.Queue(maxsize=5))
        with patch.object(config, "BASE_URL", "https://example.com"):
            app = build_web_app(application)

        async def post(data):
            payload = MagicMock(); payload.readany = AsyncMock(side_effect=[json.dumps(data).encode(), b""])
            req = make_mocked_request("POST", "/webhook", headers={"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": config.WEBHOOK_SECRET}, payload=payload, app=app, client_max_size=app._client_max_size)
            match = await app.router.resolve(req)
            return (await match.handler(req)).status

        member = {"status": "administrator", "user": {"id": 1, "is_bot": True, "first_name": "B"}, "can_be_edited": False, "is_anonymous": False, "can_manage_chat": True, "can_delete_messages": True, "can_manage_video_chats": False, "can_restrict_members": False, "can_promote_members": False, "can_change_info": False, "can_invite_users": True, "can_post_messages": True, "can_edit_messages": True, "can_pin_messages": True, "can_manage_topics": True, "can_post_stories": False, "can_edit_stories": False, "can_delete_stories": False}
        good = {"update_id": 5, "my_chat_member": {"chat": {"id": -100123, "type": "channel", "title": "C"}, "from": {"id": 7, "is_bot": False, "first_name": "R"}, "date": 1, "old_chat_member": {**member, "status": "left"}, "new_chat_member": member}}
        self.assertEqual(await post(good), 200)
        self.assertEqual(application.update_queue.get_nowait().my_chat_member.new_chat_member.status, "administrator")
        self.assertEqual(await post({"update_id": 6, "my_chat_member": {"chat": {}}}), 400)


if __name__ == "__main__":
    unittest.main()
