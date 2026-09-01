import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from trade_agent import __version__
from trade_agent.api.app import create_app
from trade_agent.api.rate_limit import RateLimitExceeded, TenantRateLimiter
from trade_agent.config import Settings


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TenantRateLimiterTests(unittest.TestCase):
    def test_tenants_have_independent_fixed_windows(self) -> None:
        clock = MutableClock()
        limiter = TenantRateLimiter(
            requests_per_window=2,
            window_seconds=60,
            clock=clock,
        )

        limiter.check("tenant-a")
        limiter.check("tenant-a")
        limiter.check("tenant-b")

        with self.assertRaises(RateLimitExceeded) as blocked:
            limiter.check("tenant-a")
        self.assertEqual(blocked.exception.retry_after_seconds, 60)

        clock.now = 59.1
        with self.assertRaises(RateLimitExceeded) as nearly_reset:
            limiter.check("tenant-a")
        self.assertEqual(nearly_reset.exception.retry_after_seconds, 1)

        clock.now = 60
        limiter.check("tenant-a")

    def test_non_positive_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requests_per_window"):
            TenantRateLimiter(requests_per_window=0, window_seconds=60)
        with self.assertRaisesRegex(ValueError, "window_seconds"):
            TenantRateLimiter(requests_per_window=1, window_seconds=0)

        with self.assertRaises(ValidationError):
            Settings(environment="test", api_rate_limit_requests=0)
        with self.assertRaises(ValidationError):
            Settings(environment="test", api_rate_limit_window_seconds=3_601)

    def test_concurrent_requests_cannot_exceed_the_window_budget(self) -> None:
        limiter = TenantRateLimiter(requests_per_window=10, window_seconds=60)

        def attempt() -> bool:
            try:
                limiter.check("tenant-a")
            except RateLimitExceeded:
                return False
            return True

        with ThreadPoolExecutor(max_workers=20) as executor:
            accepted = list(executor.map(lambda _: attempt(), range(100)))

        self.assertEqual(sum(accepted), 10)


class ApiRateLimitTests(unittest.TestCase):
    api_key = "tenant-a-rate-test-key-000000000001"
    rotated_api_key = "tenant-a-rate-test-key-000000000002"
    other_api_key = "tenant-b-rate-test-key-000000000003"

    def test_authenticated_tenant_limit_returns_stable_429(self) -> None:
        engine = create_engine(
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
                hashlib.sha256(self.api_key.encode()).hexdigest(): "tenant-a",
                hashlib.sha256(self.rotated_api_key.encode()).hexdigest(): "tenant-a",
                hashlib.sha256(self.other_api_key.encode()).hexdigest(): "tenant-b",
            },
            api_rate_limit_requests=2,
            api_rate_limit_window_seconds=60,
        )

        with TestClient(create_app(settings=settings, engine=engine)) as client:
            for _ in range(3):
                self.assertEqual(client.get("/health").status_code, 200)

            headers = {"X-API-Key": self.api_key}
            self.assertEqual(client.get("/api/v1/opportunities", headers=headers).status_code, 200)
            self.assertEqual(client.get("/api/v1/opportunities", headers=headers).status_code, 200)

            blocked = client.get(
                "/api/v1/opportunities",
                headers={
                    "X-API-Key": self.rotated_api_key,
                    "X-Correlation-ID": "343f80ba-1d47-4a56-aee5-901cbff70cb2",
                },
            )
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "60")
            self.assertEqual(
                blocked.headers["X-Correlation-ID"],
                "343f80ba-1d47-4a56-aee5-901cbff70cb2",
            )
            self.assertEqual(blocked.json()["code"], "RATE_LIMIT_EXCEEDED")
            self.assertNotIn("tenant-a", blocked.text)

            other_tenant = client.get(
                "/api/v1/opportunities",
                headers={"X-API-Key": self.other_api_key},
            )
            self.assertEqual(other_tenant.status_code, 200)

            invalid = client.get(
                "/api/v1/opportunities",
                headers={"X-API-Key": "invalid-rate-test-key-000000000000"},
            )
            self.assertEqual(invalid.status_code, 401)

    def test_openapi_version_uses_package_version(self) -> None:
        app = create_app(settings=Settings(environment="test"))

        self.assertEqual(app.version, __version__)


if __name__ == "__main__":
    unittest.main()
