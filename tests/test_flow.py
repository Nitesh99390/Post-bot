"""Offline tests: validation, webhook boundary, Supabase store and app lifecycle."""

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from telegram.error import NetworkError
from telegram.ext import Application

from bot import config
from bot.store import MemoryStore, StoreError
from bot.post import (
    TEXT_LIMIT,
    Post,
    normalize_url,
    parse_quick_buttons,
    plain_len,
)
from main import build_web_app, run

USER = {"id": 42, "is_bot": False, "first_name": "Ravi"}
CHAT = {"id": 42, "type": "private", "first_name": "Ravi"}


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
        button = application.bot.set_chat_menu_button.call_args.kwargs["menu_button"]
        if webhook:  # the menu button opens the Mini App served from BASE_URL
            self.assertEqual(button.type, "web_app")
            self.assertEqual(button.web_app.url, "https://example.com/app/")
        else:
            self.assertEqual(button.type, "commands")
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
