import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from trade_agent.api.app import create_app
from trade_agent.config import Settings


class FailingReferenceRateProvider:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def latest_reference_rate(self, quote_currency: str):
        raise RuntimeError(f"provider exploded with {self.secret} for {quote_currency}")


class InternalErrorContractTests(unittest.TestCase):
    def test_unexpected_exception_is_generic_correlated_and_non_cacheable(self) -> None:
        secret = "COMMERCIAL-SECRET-IN-EXCEPTION-998877"
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
        )
        correlation_id = "343f80ba-1d47-4a56-aee5-901cbff70cb2"

        with TestClient(
            create_app(
                settings=settings,
                engine=engine,
                reference_rates=FailingReferenceRateProvider(secret),
            ),
            raise_server_exceptions=False,
        ) as client:
            response = client.get(
                "/api/v1/reference-rates/ecb/USD",
                headers={"X-Correlation-ID": correlation_id},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {
                "code": "INTERNAL_ERROR",
                "message": "unexpected server error",
                "correlation_id": correlation_id,
            },
        )
        self.assertEqual(response.headers["X-Correlation-ID"], correlation_id)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn(secret, response.text)
        self.assertNotIn("RuntimeError", response.text)


if __name__ == "__main__":
    unittest.main()
