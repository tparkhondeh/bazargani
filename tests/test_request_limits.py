import asyncio
import json
import unittest

from starlette.types import Message, Receive, Scope, Send

from trade_agent.api.middleware import RequestBodyLimitMiddleware


class RequestBodyLimitMiddlewareTests(unittest.TestCase):
    def test_chunked_body_without_content_length_is_rejected_before_app(self) -> None:
        app_called = False

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal app_called
            app_called = True

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("test", 443),
            "state": {"correlation_id": "343f80ba-1d47-4a56-aee5-901cbff70cb2"},
        }
        incoming = iter(
            [
                {"type": "http.request", "body": b"a" * 700, "more_body": True},
                {"type": "http.request", "body": b"b" * 700, "more_body": False},
            ]
        )
        sent: list[Message] = []

        async def receive() -> Message:
            return next(incoming)

        async def send(message: Message) -> None:
            sent.append(message)

        asyncio.run(RequestBodyLimitMiddleware(app, max_body_bytes=1024)(scope, receive, send))

        self.assertFalse(app_called)
        self.assertEqual(sent[0]["status"], 413)
        response_body = json.loads(sent[1]["body"])
        self.assertEqual(response_body["code"], "REQUEST_TOO_LARGE")
        self.assertEqual(
            response_body["correlation_id"],
            "343f80ba-1d47-4a56-aee5-901cbff70cb2",
        )

    def test_body_within_limit_is_replayed_without_changes(self) -> None:
        consumed = bytearray()

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            while True:
                message = await receive()
                consumed.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("test", 443),
            "state": {},
        }
        incoming = iter(
            [
                {"type": "http.request", "body": b"hello ", "more_body": True},
                {"type": "http.request", "body": b"world", "more_body": False},
            ]
        )
        sent: list[Message] = []

        async def receive() -> Message:
            return next(incoming)

        async def send(message: Message) -> None:
            sent.append(message)

        asyncio.run(RequestBodyLimitMiddleware(app, max_body_bytes=1024)(scope, receive, send))

        self.assertEqual(consumed, b"hello world")
        self.assertEqual(sent[0]["status"], 204)


if __name__ == "__main__":
    unittest.main()
