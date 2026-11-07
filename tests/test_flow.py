"""Offline regression tests for the editor, validation and webhook boundary."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from telegram import Update
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter
from telegram.ext import Application
from telegram.request import BaseRequest

from bot import config
from bot import handlers as h
from bot.store import MAX_SAVED_POSTS, MemoryStore, StoreError
from bot.post import (
    CAPTION_LIMIT,
    MAX_BUTTONS,
    TEXT_LIMIT,
    Post,
    normalize_url,
    parse_quick_buttons,
    plain_len,
)
from main import build_web_app, run

USER = {"id": 42, "is_bot": False, "first_name": "Ravi"}
CHAT = {"id": 42, "type": "private", "first_name": "Ravi"}
PHOTO = [{"file_id": "P1", "file_unique_id": "p", "width": 1, "height": 1}]
GIF = {"file_id": "G1", "file_unique_id": "g", "width": 1, "height": 1, "duration": 1}
STICKER = {
    "file_id": "S1",
    "file_unique_id": "s",
    "width": 1,
    "height": 1,
    "is_animated": False,
    "is_video": False,
    "type": "regular",
}


def update_data(update_id=1, **content):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": CHAT,
            "from": USER,
            **content,
        },
    }


class FakeRequest(BaseRequest):
    def __init__(self):
        self.calls = []
        self.failure = None
        self.sequence = 0

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    @property
    def read_timeout(self):
        return 5

    async def do_request(self, url, method, request_data=None, **kwargs):
        name = url.rsplit("/", 1)[-1]
        params = request_data.json_parameters if request_data else {}
        params = {
            k: json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v
            for k, v in params.items()
        }
        self.sequence += 1
        if name == "getMe":
            result = {
                "id": 1,
                "is_bot": True,
                "first_name": "Bot",
                "username": "test_bot",
            }
        else:
            self.calls.append((name, params))
            if self.failure:
                error, self.failure = self.failure, None
                raise error
            result = {"message_id": self.sequence, "date": 0, "chat": CHAT, "text": "x"}
        return 200, json.dumps({"ok": True, "result": result}).encode()


def keyboard(call):
    return [
        [button["text"] for button in row]
        for row in call[1].get("reply_markup", {}).get("keyboard", [])
    ]


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.dict("os.environ", {"PTB_TIMEDELTA": "1"}))
        self.transport = FakeRequest()
        self.app = (
            Application.builder()
            .token("123:TEST")
            .request(self.transport)
            .get_updates_request(FakeRequest())
            .build()
        )
        h.register(self.app)
        self.errors = []

        async def capture_error(update, context):
            self.errors.append(context.error)

        self.app.add_error_handler(capture_error)
        await self.app.initialize()
        self.sequence = 0

    async def asyncTearDown(self):
        await self.app.shutdown()
        self.assertEqual(
            self.errors, [], "Unhandled errors must not be hidden by the global handler"
        )

    async def send(self, text=None, user_id=42, **content):
        self.transport.calls.clear()
        self.sequence += 1
        if text is not None:
            content["text"] = text
            if text.startswith("/"):
                content["entities"] = [
                    {"type": "bot_command", "offset": 0, "length": len(text.split()[0])}
                ]
        data = update_data(self.sequence, **content)
        if user_id != 42:
            data["message"]["chat"] = {**CHAT, "id": user_id}
            data["message"]["from"] = {**USER, "id": user_id}
        await self.app.process_update(Update.de_json(data, self.app.bot))
        return list(self.transport.calls)

    def store(self):
        return self.app.bot_data["store"]

    def post(self, user_id=42):
        return self.app.user_data[user_id][h.K_POST]

    async def draft(self, **content):
        await self.send("/new")
        return await self.send(**(content or {"text": "Original"}))

    async def add_button(self, name="Join Channel", link="@mychannel", color="Blue"):
        await self.send(h.BTN_BUTTON)
        await self.send(name)
        await self.send(link)
        return await self.send(color)

    async def test_start_has_only_native_create_button(self):
        calls = await self.send("/start")
        self.assertEqual(keyboard(calls[-1]), [[h.BTN_CREATE]])
        self.assertNotIn("web_app", json.dumps(calls))
        self.assertIn("\n", calls[-1][1]["text"])

    async def test_gif_text_button_finish_flow(self):
        await self.send(h.BTN_CREATE)
        calls = await self.send(
            animation=GIF, document={"file_id": "G1", "file_unique_id": "g"}
        )
        self.assertEqual(calls[0][0], "sendAnimation")
        self.assertEqual(keyboard(calls[-1])[0], [h.BTN_TEXT, h.BTN_BUTTON])
        await self.send(h.BTN_TEXT)
        calls = await self.send("Hello <world> & friends")
        self.assertEqual(calls[0][1]["caption"], "Hello &lt;world&gt; &amp; friends")
        calls = await self.add_button(color="Green")
        self.assertEqual(
            calls[0][1]["reply_markup"]["inline_keyboard"],
            [
                [
                    {
                        "text": "Join Channel",
                        "url": "https://t.me/mychannel",
                        "style": "success",
                    }
                ]
            ],
        )
        calls = await self.send(h.BTN_DONE)
        self.assertEqual(calls[0][0], "sendAnimation")
        self.assertIn("Ready to share", calls[-1][1]["text"])
        self.assertEqual(dict(self.app.user_data[42]), {})
        self.assertEqual(keyboard(calls[-1]), [[h.BTN_CREATE]])

    async def test_formatted_text_is_preserved_and_replaced(self):
        calls = await self.draft(
            text="Title", entities=[{"type": "bold", "offset": 0, "length": 5}]
        )
        self.assertEqual(calls[0][1]["text"], "<b>Title</b>")
        await self.send(h.BTN_TEXT)
        await self.send("Replacement")
        self.assertEqual(self.post().text, "Replacement")

    async def test_photo_caption_and_media_replacement(self):
        calls = await self.draft(photo=PHOTO, caption="Original")
        self.assertEqual(calls[0][1]["caption"], "Original")
        await self.send(video={**GIF, "file_id": "V1"})
        self.assertEqual(
            (self.post().media_type, self.post().text), ("video", "Original")
        )
        await self.send(photo=PHOTO, caption="New caption")
        self.assertEqual(self.post().text, "New caption")

    async def test_sticker_text_is_delivered_separately(self):
        calls = await self.draft(sticker=STICKER)
        self.assertEqual(calls[0][0], "sendSticker")
        await self.send(h.BTN_TEXT)
        calls = await self.send("Hello")
        self.assertEqual(
            [c[0] for c in calls], ["sendSticker", "sendMessage", "sendMessage"]
        )

    async def test_caption_boundary_and_long_caption_split(self):
        await self.draft(photo=PHOTO)
        for length in (CAPTION_LIMIT, CAPTION_LIMIT + 1):
            await self.send(h.BTN_TEXT)
            calls = await self.send("a" * length)
            self.assertEqual("caption" in calls[0][1], length <= CAPTION_LIMIT)
            self.assertEqual(len(calls), 2 if length <= CAPTION_LIMIT else 3)

    async def test_over_limit_text_does_not_replace_draft(self):
        await self.draft()
        await self.send(h.BTN_TEXT)
        for text in ("a" * (TEXT_LIMIT + 1), "\U0001f600" * (TEXT_LIMIT // 2 + 1)):
            calls = await self.send(text)
            self.assertIn("too long", calls[-1][1]["text"])
            self.assertEqual(self.post().text, "Original")
        await self.send("a" * TEXT_LIMIT)
        self.assertEqual(len(self.post().text), TEXT_LIMIT)

    async def test_invalid_caption_is_transactional(self):
        await self.draft(photo=PHOTO, caption="Original")
        calls = await self.send(animation=GIF, caption="a" * (TEXT_LIMIT + 1))
        self.assertIn("too long", calls[-1][1]["text"])
        self.assertEqual(self.post().media_type, "photo")
        self.assertEqual(self.post().text, "Original")

    async def test_invalid_label_link_colour_and_back(self):
        await self.draft()
        await self.send(h.BTN_BUTTON)
        await self.send("x" * 65)
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_BTN_NAME)
        await self.send("Join")
        calls = await self.send("https://[broken")
        self.assertIn("valid link", calls[-1][1]["text"])
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_BTN_LINK)
        await self.send("example.com")
        await self.send("Purple")
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_BTN_COLOR)
        await self.send("/back")
        self.assertNotIn(h.K_DRAFT, self.app.user_data[42])
        self.assertEqual(self.post().text, "Original")
        self.assertEqual(self.post().buttons, [])

    async def test_button_limit_and_remove_last(self):
        await self.draft()
        for i in range(MAX_BUTTONS):
            await self.add_button(name=f"Link {i}", color="Red")
        calls = await self.send(h.BTN_BUTTON)
        self.assertEqual(len(self.post().buttons), MAX_BUTTONS)
        self.assertNotIn(
            h.BTN_BUTTON, [label for row in keyboard(calls[-1]) for label in row]
        )
        calls = await self.send(h.BTN_REMOVE)
        self.assertEqual(len(self.post().buttons), MAX_BUTTONS - 1)
        self.assertIn(
            h.BTN_BUTTON, [label for row in keyboard(calls[-1]) for label in row]
        )

    async def test_commands_and_user_isolation(self):
        await self.draft()
        await self.send("/new", user_id=77)
        await self.send("Other draft", user_id=77)
        await self.send("/help")
        await self.send("/unknown")
        await self.send("/cancel")
        self.assertEqual(dict(self.app.user_data[42]), {})
        self.assertEqual(self.post(77).text, "Other draft")
        await self.send("/new", user_id=77)
        self.assertNotIn(h.K_POST, self.app.user_data[77])

    async def test_labels_are_content_inside_edit_steps(self):
        await self.draft(text=h.BTN_CREATE)
        self.assertEqual(self.post().text, h.BTN_CREATE)
        await self.send(h.BTN_TEXT)
        await self.send(h.BTN_DONE)
        self.assertEqual(self.post().text, h.BTN_DONE)

    async def test_unsupported_media_and_empty_preview(self):
        await self.send("/preview")
        calls = await self.send(location={"latitude": 1.0, "longitude": 2.0})
        self.assertIn("Send text", calls[-1][1]["text"])
        self.assertTrue(self.post().is_empty())
        await self.send("/back")
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_MEDIA)

    async def test_service_data_and_group_messages_are_ignored(self):
        await self.draft()
        calls = await self.send(web_app_data={"data": "invalid", "button_text": "old"})
        self.assertEqual(calls, [])
        self.assertEqual(self.post().text, "Original")
        calls = await self.send(
            text="/new", chat={"id": -100, "type": "supergroup", "title": "Group"}
        )
        self.assertEqual(calls, [])
        self.assertEqual(self.post().text, "Original")

    async def test_preview_failures_preserve_draft_and_offer_recovery(self):
        for error in (BadRequest("rejected"), NetworkError("offline"), RetryAfter(5)):
            with self.subTest(error=type(error).__name__):
                await self.send("/new")
                self.transport.failure = error
                calls = await self.send("Keep me")
                self.assertEqual(self.post().text, "Keep me")
                self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_MENU)
                self.assertIn("saved", calls[-1][1]["text"])
                self.assertIn(
                    h.BTN_PREVIEW,
                    [label for row in keyboard(calls[-1]) for label in row],
                )

    async def test_failed_finish_does_not_discard_draft(self):
        await self.draft()
        self.transport.failure = NetworkError("offline")
        calls = await self.send(h.BTN_DONE)
        self.assertEqual(self.post().text, "Original")
        self.assertIn("before retrying", calls[-1][1]["text"])
        await self.send(h.BTN_DONE)
        self.assertEqual(dict(self.app.user_data[42]), {})

    async def test_rejected_button_can_be_removed(self):
        await self.draft()
        await self.send(h.BTN_BUTTON)
        await self.send("Website")
        await self.send("example.com")
        self.transport.failure = BadRequest("invalid button")
        await self.send("Blue")
        self.assertEqual(len(self.post().buttons), 1)
        await self.send(h.BTN_REMOVE)
        self.assertEqual(self.post().buttons, [])

    async def test_first_message_resets_stale_profile_menu_button(self):
        calls = await self.send("/start")
        menu = [c for c in calls if c[0] == "setChatMenuButton"]
        self.assertEqual(len(menu), 1)
        self.assertEqual(str(menu[0][1]["chat_id"]), "42")
        self.assertEqual(menu[0][1]["menu_button"]["type"], "commands")
        calls = await self.send("/help")
        self.assertNotIn("setChatMenuButton", [c[0] for c in calls])
        self.assertNotIn("My profile", json.dumps(calls))

    async def test_keyboards_keep_the_same_buttons(self):
        await self.draft()
        calls = await self.add_button()
        self.assertEqual(
            keyboard(calls[-1]),
            [[h.BTN_TEXT, h.BTN_BUTTON], [h.BTN_PREVIEW, h.BTN_DONE], [h.BTN_REMOVE]],
        )

    async def test_old_plain_labels_still_work(self):
        await self.draft()
        await self.send("Add Button")
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_BTN_NAME)
        await self.send("Join")
        await self.send("@mychannel")
        await self.send("green")
        self.assertEqual(self.post().buttons[0]["color"], "green")

    async def test_quick_multi_button_entry(self):
        await self.draft()
        await self.send(h.BTN_BUTTON)
        calls = await self.send("Join Channel - @mychannel\nWebsite | example.com")
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_BTN_COLOR)
        self.assertIn("Join Channel", calls[-1][1]["text"])
        await self.send("🔴 Red")
        self.assertEqual(
            self.post().buttons,
            [
                {"text": "Join Channel", "url": "https://t.me/mychannel", "color": "red"},
                {"text": "Website", "url": "https://example.com", "color": "red"},
            ],
        )

    async def test_quick_button_from_editor_menu(self):
        await self.draft()
        await self.send("Shop - example.com/shop")
        await self.send("Blue")
        self.assertEqual(self.post().buttons[0]["url"], "https://example.com/shop")

    async def test_forwarded_post_imports_buttons(self):
        await self.send("/new")
        await self.send(
            text="Big sale",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Buy", "url": "https://example.com", "style": "success"}],
                    [{"text": "Cb", "callback_data": "x"}],
                ]
            },
        )
        self.assertEqual(
            self.post().buttons,
            [{"text": "Buy", "url": "https://example.com", "color": "green"}],
        )

    async def test_new_media_types(self):
        for kind, payload, method in (
            ("document", {"file_id": "D1", "file_unique_id": "d"}, "sendDocument"),
            ("voice", {"file_id": "V1", "file_unique_id": "v", "duration": 1}, "sendVoice"),
            ("audio", {"file_id": "A1", "file_unique_id": "a", "duration": 1}, "sendAudio"),
        ):
            with self.subTest(kind=kind):
                calls = await self.draft(**{kind: payload, "caption": "Hi"})
                self.assertEqual(calls[0][0], method)
                self.assertEqual(calls[0][1]["caption"], "Hi")
        calls = await self.draft(
            video_note={"file_id": "N1", "file_unique_id": "n", "length": 1, "duration": 1}
        )
        self.assertEqual(calls[0][0], "sendVideoNote")

    async def test_save_list_open_delete_templates(self):
        await self.draft(text="Promo text")
        await self.add_button()
        calls = await self.send("/save Promo")
        self.assertIn("Promo</b> saved", calls[-1][1]["text"])
        post_id = next(iter(self.store().posts))
        calls = await self.send("/save Promo")
        self.assertIn("updated", calls[-1][1]["text"])
        self.assertEqual(len(self.store().posts), 1)
        await self.send("/cancel")
        calls = await self.send("/posts")
        self.assertIn(f"/open_{post_id}", calls[-1][1]["text"])
        calls = await self.send(f"/open_{post_id}")
        self.assertEqual(calls[0][1]["text"], "Promo text")
        self.assertEqual(len(self.post().buttons), 1)
        self.assertEqual(self.app.user_data[42][h.K_STATE], h.S_MENU)
        # Other users cannot open or delete it.
        calls = await self.send(f"/open_{post_id}", user_id=77)
        self.assertIn("doesn't exist", calls[-1][1]["text"])
        calls = await self.send(f"/del_{post_id}", user_id=77)
        self.assertIn("doesn't exist", calls[-1][1]["text"])
        calls = await self.send(f"/del_{post_id}")
        self.assertIn("deleted", calls[-1][1]["text"])
        self.assertEqual(self.store().posts, {})

    async def test_save_requires_draft_and_respects_limit(self):
        calls = await self.send("/save")
        self.assertIn("Nothing to save", calls[-1][1]["text"])
        await self.draft(text="First line\nmore")
        await self.send("/save")
        self.assertEqual(next(iter(self.store().posts.values()))["name"], "First line")
        for i in range(MAX_SAVED_POSTS - 1):
            await self.store().save_post(42, f"t{i}", self.post().to_dict())
        calls = await self.send("/save another")
        self.assertIn("Delete one", calls[-1][1]["text"])

    async def test_storage_failure_keeps_draft(self):
        await self.draft()
        self.store().save_post = AsyncMock(side_effect=StoreError("network"))
        calls = await self.send("/save x")
        self.assertIn("Saving failed", calls[-1][1]["text"])
        self.assertEqual(self.post().text, "Original")

    async def test_finish_counts_posts_and_stats(self):
        await self.draft()
        calls = await self.send(h.BTN_DONE)
        self.assertIn("post <b>#1</b>", calls[-1][1]["text"])
        calls = await self.send("/stats")
        self.assertIn("Posts created: <b>1</b>", calls[-1][1]["text"])
        calls = await self.send("/start")
        self.assertIn("Posts created: <b>1</b>", calls[-1][1]["text"])

    async def test_session_is_persisted_and_restored(self):
        await self.draft(text="Survives restart")
        self.assertEqual(
            self.store().sessions[42]["post"]["text"], "Survives restart"
        )
        # Simulate a restart: fresh in-memory state, same store.
        store = self.store()
        self.app.user_data[42].clear()
        self.app.bot_data.clear()
        self.app.bot_data["store"] = store
        await self.send("/back")
        self.assertEqual(self.post().text, "Survives restart")
        await self.send("/cancel")
        self.assertNotIn(42, store.sessions)

    async def test_link_preview_toggle(self):
        await self.draft(text="https://example.com")
        calls = await self.send("/linkpreview")
        sent = [c for c in calls if c[0] == "sendMessage" and c[1]["text"] == "https://example.com"]
        self.assertTrue(sent[0][1]["link_preview_options"]["is_disabled"])
        self.assertFalse(self.post().link_preview)

    async def test_channel_and_publish(self):
        calls = await self.send("/publish")
        self.assertIn("Nothing to publish", calls[-1][1]["text"])
        await self.draft()
        calls = await self.send("/publish")
        self.assertIn("No channel set", calls[-1][1]["text"])
        self.assertEqual(self.post().text, "Original")
        await self.store().update_profile(42, default_channel="@mychannel")
        calls = await self.send("/publish")
        self.assertEqual(calls[0][0], "sendMessage")
        self.assertEqual(calls[0][1]["chat_id"], "@mychannel")
        self.assertIn("t.me/mychannel/", calls[-1][1]["text"])
        self.assertNotIn(h.K_POST, self.app.user_data[42])

    async def test_publish_failure_keeps_draft(self):
        await self.draft()
        self.transport.failure = Forbidden("not admin")
        calls = await self.send("/publish @mychannel")
        self.assertIn("admin", calls[-1][1]["text"])
        self.assertEqual(self.post().text, "Original")

    async def test_channel_command_validation(self):
        calls = await self.send("/channel")
        self.assertIn("No channel set", calls[-1][1]["text"])
        calls = await self.send("/channel not a channel")
        self.assertIn("Use a channel", calls[-1][1]["text"])
        self.transport.failure = BadRequest("chat not found")
        await self.send("/channel @missing_chan")
        self.assertIsNone((await self.store().get_profile(42)).get("default_channel"))
        await self.send("/channel off")
        self.assertIsNone((await self.store().get_profile(42)).get("default_channel"))


class ValidationTests(unittest.TestCase):
    def test_url_normalization(self):
        cases = {
            "example.com": "https://example.com",
            "@channelname": "https://t.me/channelname",
            "HTTPS://EXAMPLE.COM/a?b=1#c": "https://example.com/a?b=1#c",
            "https://b\u00fccher.de": "https://xn--bcher-kva.de",
            "http://example.com:8080": "http://example.com:8080",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_url(raw), expected)

    def test_unsafe_and_malformed_urls(self):
        values = [
            "",
            "hello",
            "not a link",
            "https://[broken",
            "https://example.com:abc",
            "https://example.com:65536",
            "https://example.com:0",
            "https://user:pass@example.com",
            "javascript:alert(1)",
            "tg://user?id=1",
            "ftp://example.com",
            "https://.example.com",
            "https://a..com",
            "https://-host.com",
            "https://example.com/x\ny",
            "https://exam\x00ple.com",
            "https://example.com\\@evil.com",
            "https://example.com/" + "x" * 2048,
        ]
        for raw in values:
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_url(raw))

    def test_quick_button_parsing(self):
        self.assertEqual(
            parse_quick_buttons("A - example.com\nB | @chan_name"),
            [
                {"text": "A", "url": "https://example.com"},
                {"text": "B", "url": "https://t.me/chan_name"},
            ],
        )
        for raw in ("Just text", "A - example.com\nnot a button", "", "A - nope"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_quick_buttons(raw))

    def test_post_roundtrip(self):
        post = Post(
            media_type="photo",
            file_id="P",
            text="<b>x</b>",
            buttons=[{"text": "A", "url": "https://a.com", "color": "red"}],
            link_preview=False,
        )
        self.assertEqual(Post.from_dict(post.to_dict()), post)
        for bad in (None, [], {"media_type": "bad", "file_id": "x"}, {"buttons": [{}]}):
            self.assertIsNone(Post.from_dict(bad))

    def test_utf16_and_escaped_html_length(self):
        self.assertEqual(plain_len("<b>A</b>&amp;\U0001f600"), 4)
        self.assertEqual(plain_len("&lt;b&gt;"), 3)

    def test_invalid_post_models(self):
        for post in (
            Post(media_type="bad", file_id="id"),
            Post(media_type="photo"),
            Post(file_id="id"),
            Post(text="x" * (TEXT_LIMIT + 1)),
            Post(buttons=[{"text": "", "url": "https://example.com", "color": "blue"}]),
        ):
            with self.subTest(post=post), self.assertRaises(ValueError):
                post.validate()

    def test_configuration_validation(self):
        with patch.multiple(
            config, BOT_TOKEN="123:TEST", PORT="10000", BASE_URL="https://example.com"
        ):
            config.validate()
            for key, values in {
                "PORT": ["oops", "0", "65536"],
                "BOT_TOKEN": [""],
                "BASE_URL": [
                    "http://example.com",
                    "https://example.com:3000",
                    "https://u:p@example.com",
                    "https://example.com?x=1",
                ],
            }.items():
                for value in values:
                    with (
                        self.subTest(key=key, value=value),
                        patch.object(config, key, value),
                        self.assertRaises(RuntimeError),
                    ):
                        config.validate()


class WebhookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Application.builder().token("123:TEST").build().bot
        self.application = SimpleNamespace(
            bot=self.bot, running=True, update_queue=asyncio.Queue(maxsize=1)
        )
        with patch.object(config, "BASE_URL", "https://example.com"):
            self.webapp = build_web_app(self.application)

    async def request(
        self,
        path="/webhook",
        data=None,
        secret=None,
        method="POST",
        body=None,
        app=None,
    ):
        headers = {
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": config.WEBHOOK_SECRET
            if secret is None
            else secret,
        }
        payload = MagicMock()
        payload.readany = AsyncMock()
        payload.readany.side_effect = [
            body if body is not None else json.dumps(data).encode(),
            b"",
        ]
        target = app if app is not None else self.webapp
        request = make_mocked_request(
            method,
            path,
            headers=headers,
            payload=payload,
            app=target,
            client_max_size=target._client_max_size,
        )
        match = await target.router.resolve(request)
        try:
            return await match.handler(request)
        except web.HTTPException as error:
            return error

    async def test_health_readiness_and_removed_app(self):
        self.assertEqual((await self.request("/health", method="GET")).status, 200)
        self.application.running = False
        self.assertEqual((await self.request("/health", method="GET")).status, 503)
        self.assertEqual((await self.request("/app", method="GET")).status, 404)

    async def test_authentication(self):
        for secret in ("", "wrong", "\u00e9"):
            self.assertEqual(
                (await self.request(data=update_data(), secret=secret)).status, 403
            )
        self.assertTrue(self.application.update_queue.empty())

    async def test_not_running_and_wrong_method(self):
        self.application.running = False
        self.assertEqual((await self.request(data=update_data())).status, 503)
        self.assertEqual((await self.request(method="GET")).status, 405)

    async def test_valid_update_and_duplicate(self):
        for _ in range(2):
            self.assertEqual(
                (await self.request(data=update_data(text="hello"))).status, 200
            )
        self.assertEqual(self.application.update_queue.qsize(), 1)
        self.assertEqual(
            self.application.update_queue.get_nowait().message.text, "hello"
        )

    async def test_queue_backpressure_allows_retry(self):
        self.assertEqual((await self.request(data=update_data(1))).status, 200)
        response = await self.request(data=update_data(2))
        self.assertEqual(response.status, 503)
        self.assertEqual(response.headers["Retry-After"], "5")
        self.application.update_queue.get_nowait()
        self.assertEqual((await self.request(data=update_data(2))).status, 200)
        self.assertEqual(self.application.update_queue.get_nowait().update_id, 2)

    async def test_invalid_payloads(self):
        values = [
            None,
            [],
            "text",
            {},
            {"update_id": True},
            {"update_id": -1},
            {"update_id": 1},
            {"update_id": 1, "message": "bad"},
            {"update_id": 1, "message": {}},
            update_data(chat={}),
            update_data(date="bad"),
            update_data(photo=[{}]),
            update_data(date=10**100),
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual((await self.request(data=value)).status, 400)
        self.assertEqual((await self.request(body=b"invalid json")).status, 400)
        self.assertTrue(self.application.update_queue.empty())

    async def test_body_limit(self):
        self.assertEqual((await self.request(body=b"x" * (256 * 1024 + 1))).status, 413)
        self.assertTrue(self.application.update_queue.empty())

    async def test_polling_has_no_webhook_route(self):
        with patch.object(config, "BASE_URL", ""):
            polling_app = build_web_app(self.application)
        self.assertEqual((await self.request(app=polling_app)).status, 404)


class SupabaseStoreTests(unittest.IsolatedAsyncioTestCase):
    async def make(self, handler):
        import httpx

        from bot.store import SupabaseStore

        store = SupabaseStore("https://x.supabase.co", "sb_publishable_test")
        await store._client.aclose()
        store._client = httpx.AsyncClient(
            base_url="https://x.supabase.co/rest/v1",
            headers={"apikey": "sb_publishable_test"},
            transport=httpx.MockTransport(handler),
        )
        return store

    async def test_missing_tables_fall_back_to_memory(self):
        import httpx

        from bot import store as store_module

        def handler(request):
            return httpx.Response(404, json={"message": "Could not find the table"})

        original = store_module.SupabaseStore
        made = await self.make(handler)
        with patch.object(store_module, "SupabaseStore", return_value=made):
            result = await store_module.create_store("https://x.supabase.co", "k")
        self.assertIsInstance(result, MemoryStore)
        self.assertIs(store_module.SupabaseStore, original)

    async def test_requests_are_scoped_and_upserted(self):
        import httpx

        seen = []

        def handler(request):
            seen.append(request)
            if request.method == "GET" and request.url.path.endswith("/saved_posts"):
                return httpx.Response(200, json=[])
            if request.method == "POST" and request.url.path.endswith("/saved_posts"):
                return httpx.Response(201, json=[{"id": 9}])
            return httpx.Response(201)

        store = await self.make(handler)
        await store.save_session(42, {"state": "menu"})
        upsert = seen[-1]
        self.assertEqual(upsert.url.params["on_conflict"], "user_id")
        self.assertIn("merge-duplicates", upsert.headers["Prefer"])
        self.assertEqual(json.loads(upsert.content)["user_id"], 42)
        self.assertEqual(await store.save_post(42, "Promo", {"text": "x"}), (9, False))
        self.assertTrue(all(r.url.params.get("user_id", "eq.42") == "eq.42" for r in seen))
        await store.close()

    async def test_http_errors_raise_store_error(self):
        import httpx

        store = await self.make(lambda request: httpx.Response(500, json={"message": "boom"}))
        with self.assertRaises(StoreError):
            await store.load_session(1)
        await store.close()


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, webhook=True, fail=False):
        application = MagicMock()
        application.running = False
        application.updater.running = False
        application.__aenter__.return_value = application
        application.bot.set_my_commands = AsyncMock()
        application.bot.set_chat_menu_button = AsyncMock()
        application.bot.set_webhook = AsyncMock(
            side_effect=NetworkError("offline") if fail else None
        )
        application.bot.delete_webhook = AsyncMock()

        async def start():
            application.running = True

        async def stop_app():
            application.running = False

        async def polling():
            application.updater.running = True

        application.start = AsyncMock(side_effect=start)
        application.stop = AsyncMock(side_effect=stop_app)
        application.updater.start_polling = AsyncMock(side_effect=lambda **kwargs: None)
        application.updater.stop = AsyncMock()
        if not webhook:

            async def start_polling(**kwargs):
                await polling()

            application.updater.start_polling.side_effect = start_polling

        builder = MagicMock()
        for method in (
            "token",
            "update_queue",
            "concurrent_updates",
            "connect_timeout",
            "read_timeout",
            "write_timeout",
            "pool_timeout",
        ):
            getattr(builder, method).return_value = builder
        builder.build.return_value = application
        runner = SimpleNamespace(setup=AsyncMock(), cleanup=AsyncMock())
        site = SimpleNamespace(start=AsyncMock())
        stop = asyncio.Event()
        stop.set()
        loop = asyncio.get_running_loop()
        with (
            patch.multiple(
                config,
                BOT_TOKEN="123:TEST",
                PORT="10000",
                BASE_URL="https://example.com" if webhook else "",
                STORAGE_ENABLED=False,
            ),
            patch("main.Application.builder", return_value=builder),
            patch("main.web.AppRunner", return_value=runner),
            patch("main.web.TCPSite", return_value=site),
            patch("main.asyncio.Event", return_value=stop),
            patch.object(loop, "add_signal_handler"),
            patch.object(loop, "remove_signal_handler"),
        ):
            if fail:
                with self.assertRaises(NetworkError):
                    await run()
            else:
                await run()
        runner.setup.assert_awaited_once()
        site.start.assert_awaited_once()
        self.assertGreaterEqual(runner.cleanup.await_count, 1)
        application.stop.assert_awaited_once()
        application.__aexit__.assert_awaited_once()
        application.bot.set_chat_menu_button.assert_awaited_once()
        self.assertEqual(
            application.bot.set_chat_menu_button.call_args.kwargs["menu_button"].type,
            "commands",
        )
        if webhook:
            application.bot.set_webhook.assert_awaited_once()
            self.assertFalse(
                application.bot.set_webhook.call_args.kwargs["drop_pending_updates"]
            )
            application.updater.start_polling.assert_not_awaited()
        else:
            application.bot.delete_webhook.assert_awaited_once_with(
                drop_pending_updates=False
            )
            application.updater.start_polling.assert_awaited_once()
            application.updater.stop.assert_awaited_once()

    async def test_webhook_startup_and_shutdown(self):
        await self.exercise()

    async def test_polling_startup_and_shutdown(self):
        await self.exercise(webhook=False)

    async def test_webhook_setup_failure_cleans_up(self):
        await self.exercise(fail=True)


if __name__ == "__main__":
    unittest.main()
