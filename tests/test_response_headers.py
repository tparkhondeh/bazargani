import hashlib
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.responses import JSONResponse

from trade_agent.api.app import create_app
from trade_agent.api.response_headers import apply_response_security_headers
from trade_agent.config import Settings

EXPECTED_HEADERS = {
    "cache-control": "no-store",
    "pragma": "no-cache",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


class ResponseSecurityHeaderTests(unittest.TestCase):
    api_key = "response-header-test-key-000000000001"

    def test_vary_is_preserved_without_duplicate_api_key_entries(self) -> None:
        response = JSONResponse({}, headers={"Vary": "Origin, x-api-key"})

        apply_response_security_headers(response, path="/api/v1/opportunities")

        self.assertEqual(response.headers["Vary"], "Origin, x-api-key")

    def test_success_error_and_body_limit_responses_have_security_headers(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        settings = Settings(
            environment="test",
            database_url="sqlite+pysqlite://",
            auto_create_schema=True,
            max_request_body_bytes=1_024,
            log_level="CRITICAL",
            auth_enabled=True,
            api_key_credentials={
                hashlib.sha256(self.api_key.encode()).hexdigest(): "tenant-a",
            },
        )

        with TestClient(create_app(settings=settings, engine=engine)) as client:
            health = client.get("/health")
            protected = client.get(
                "/api/v1/opportunities",
                headers={"X-API-Key": self.api_key},
            )
            unauthorized = client.get("/api/v1/opportunities")
            forbidden = client.get(
                "/api/v1/research-review-queue",
                headers={"X-API-Key": self.api_key},
            )
            oversized = client.post(
                "/api/v1/requests/parse",
                headers={"X-API-Key": self.api_key},
                json={"text": "x" * 2_000},
            )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(protected.status_code, 200)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["code"], "AUTHORIZATION_DENIED")
        self.assertEqual(oversized.status_code, 413)
        for response in (health, protected, unauthorized, forbidden, oversized):
            with self.subTest(status=response.status_code):
                for name, expected in EXPECTED_HEADERS.items():
                    self.assertEqual(response.headers[name], expected)
        self.assertNotIn("X-API-Key", health.headers.get("Vary", ""))
        for response in (protected, unauthorized, forbidden, oversized):
            self.assertIn("X-API-Key", response.headers["Vary"])


if __name__ == "__main__":
    unittest.main()
