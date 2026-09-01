import hashlib
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from trade_agent.api.app import create_app
from trade_agent.api.response_headers import UI_CONTENT_SECURITY_POLICY
from trade_agent.config import Settings


class IntakeUiTests(unittest.TestCase):
    api_key = "ui-test-key-000000000000000000000001"

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        settings = Settings(
            environment="test",
            database_url="sqlite+pysqlite://",
            auto_create_schema=True,
            log_level="CRITICAL",
            auth_enabled=True,
            api_key_credentials={
                hashlib.sha256(self.api_key.encode()).hexdigest(): "tenant-ui",
            },
        )
        self.client_context = TestClient(create_app(settings=settings, engine=self.engine))
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_ui_shell_and_assets_are_public_but_strictly_sandboxed(self) -> None:
        for path, content_type in (
            ("/ui", "text/html"),
            ("/ui/", "text/html"),
            ("/ui/assets/app.css", "text/css"),
            ("/ui/assets/app.js", "text/javascript"),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.headers["content-type"].startswith(content_type))
                self.assertEqual(
                    response.headers["content-security-policy"],
                    UI_CONTENT_SECURITY_POLICY,
                )
                self.assertEqual(response.headers["cross-origin-opener-policy"], "same-origin")
                self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertNotIn("X-API-Key", response.headers.get("vary", ""))

    def test_html_is_rtl_and_loads_only_same_origin_external_assets(self) -> None:
        html = self.client.get("/ui").text

        self.assertIn('<html lang="fa" dir="rtl">', html)
        self.assertIn('href="/ui/assets/app.css"', html)
        self.assertIn('src="/ui/assets/app.js"', html)
        self.assertNotIn("<style", html)
        self.assertNotIn("javascript:", html.casefold())
        self.assertNotIn("http://", html.casefold())
        self.assertNotIn("https://", html.casefold())

    def test_script_does_not_persist_credentials_or_use_html_injection_sinks(self) -> None:
        script = self.client.get("/ui/assets/app.js").text

        for forbidden in (
            "localStorage",
            "sessionStorage",
            "document.cookie",
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "eval(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, script)
        self.assertIn("textContent", script)
        self.assertIn('headers["X-API-Key"] = apiKey', script)
        self.assertIn('apiKeyInput.value = ""', script)

    def test_parser_remains_authenticated_behind_public_shell(self) -> None:
        unauthorized = self.client.post(
            "/api/v1/requests/parse",
            json={"text": "۳۰۰ دستگاه، مقصد: تهران"},
        )
        authorized = self.client.post(
            "/api/v1/requests/parse",
            headers={"X-API-Key": self.api_key},
            json={"text": "۳۰۰ دستگاه اسپرسوساز، مقصد: تهران"},
        )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()["quantity"], 300)


if __name__ == "__main__":
    unittest.main()
