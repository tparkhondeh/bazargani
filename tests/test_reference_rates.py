import unittest
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError

from trade_agent.application.reference_rates import CachedReferenceRateService
from trade_agent.config import Settings
from trade_agent.domain.models import Confidence, Evidence, EvidenceClass, FXRate


class MutableClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class StubProvider:
    def __init__(self) -> None:
        self.calls = 0

    def latest_reference_rate(self, quote_currency: str) -> FXRate:
        self.calls += 1
        retrieved_at = datetime(2026, 9, 1, 8, tzinfo=UTC)
        return FXRate(
            base_currency="EUR",
            quote_currency=quote_currency,
            rate=Decimal("1.1802"),
            evidence=Evidence(
                classification=EvidenceClass.FACT,
                source_name="ECB fixture",
                source_url="https://data-api.ecb.europa.eu/service/data/EXR/test",
                retrieved_at=retrieved_at,
                raw_value="fixture",
                confidence=Confidence.HIGH,
                transformation="contract fixture",
            ),
            rate_type="ECB_DAILY_REFERENCE_INFORMATIONAL",
            effective_at=datetime(2026, 8, 31, tzinfo=UTC),
        )


class ReferenceRateCacheTests(unittest.TestCase):
    def test_provider_is_lazy_and_currency_cache_is_case_insensitive(self) -> None:
        clock = MutableClock()
        provider = StubProvider()
        factory_calls = 0

        def factory() -> StubProvider:
            nonlocal factory_calls
            factory_calls += 1
            return provider

        service = CachedReferenceRateService(factory, ttl_seconds=60, clock=clock)
        self.assertEqual(factory_calls, 0)

        first = service.latest_reference_rate(" usd ")
        second = service.latest_reference_rate("USD")

        self.assertIs(first, second)
        self.assertEqual(factory_calls, 1)
        self.assertEqual(provider.calls, 1)

    def test_expired_rate_is_refetched_without_serving_stale_data(self) -> None:
        clock = MutableClock()
        provider = StubProvider()
        service = CachedReferenceRateService(
            lambda: provider,
            ttl_seconds=60,
            clock=clock,
        )
        service.latest_reference_rate("USD")
        clock.value += 61

        service.latest_reference_rate("USD")

        self.assertEqual(provider.calls, 2)

    def test_nonpositive_ttl_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "TTL"):
            CachedReferenceRateService(StubProvider, ttl_seconds=0)

    def test_configured_ttl_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(ecb_cache_ttl_seconds=59)
        with self.assertRaises(ValidationError):
            Settings(ecb_cache_ttl_seconds=86_401)


if __name__ == "__main__":
    unittest.main()
