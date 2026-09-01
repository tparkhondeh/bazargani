import unittest
from concurrent.futures import ThreadPoolExecutor
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


class MutableObservedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 1, 8, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


class StubProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def latest_reference_rate(self, quote_currency: str) -> FXRate:
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic provider failure")
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

    def test_health_records_only_real_valid_upstream_attempts_and_cache_hits(self) -> None:
        monotonic_clock = MutableClock()
        observed_clock = MutableObservedClock()
        provider = StubProvider()
        service = CachedReferenceRateService(
            lambda: provider,
            ttl_seconds=60,
            clock=monotonic_clock,
            observed_clock=observed_clock,
        )

        initial = service.health_snapshot()
        self.assertEqual(initial.status, "NOT_OBSERVED")
        self.assertEqual(initial.observed_since, observed_clock.value)
        self.assertEqual(initial.upstream_attempt_count, 0)

        with self.assertRaisesRegex(ValueError, "non-EUR"):
            service.latest_reference_rate("EUR")
        after_invalid = service.health_snapshot()
        self.assertEqual(after_invalid.status, "NOT_OBSERVED")
        self.assertEqual(after_invalid.upstream_attempt_count, 0)

        service.latest_reference_rate("USD")
        service.latest_reference_rate(" usd ")
        successful = service.health_snapshot()
        self.assertEqual(successful.status, "LAST_ATTEMPT_SUCCEEDED")
        self.assertEqual(successful.upstream_attempt_count, 1)
        self.assertEqual(successful.success_count, 1)
        self.assertEqual(successful.failure_count, 0)
        self.assertEqual(successful.cache_hit_count, 1)

        provider.fail = True
        observed_clock.value = datetime(2026, 9, 1, 9, tzinfo=UTC)
        with self.assertRaisesRegex(RuntimeError, "synthetic provider failure"):
            service.latest_reference_rate("GBP")
        failed = service.health_snapshot()
        self.assertEqual(failed.status, "LAST_ATTEMPT_FAILED")
        self.assertEqual(failed.last_failure_at, observed_clock.value)
        self.assertEqual(failed.upstream_attempt_count, 2)
        self.assertEqual(failed.success_count, 1)
        self.assertEqual(failed.failure_count, 1)
        self.assertEqual(failed.consecutive_failure_count, 1)

        service.latest_reference_rate("USD")
        after_unrelated_cache_hit = service.health_snapshot()
        self.assertEqual(after_unrelated_cache_hit.status, "LAST_ATTEMPT_FAILED")
        self.assertEqual(after_unrelated_cache_hit.cache_hit_count, 2)

        provider.fail = False
        observed_clock.value = datetime(2026, 9, 1, 10, tzinfo=UTC)
        service.latest_reference_rate("GBP")
        recovered = service.health_snapshot()
        self.assertEqual(recovered.status, "LAST_ATTEMPT_SUCCEEDED")
        self.assertEqual(recovered.last_success_at, observed_clock.value)
        self.assertEqual(recovered.upstream_attempt_count, 3)
        self.assertEqual(recovered.success_count, 2)
        self.assertEqual(recovered.failure_count, 1)
        self.assertEqual(recovered.consecutive_failure_count, 0)

    def test_provider_construction_failure_is_an_observed_attempt(self) -> None:
        def failing_factory() -> StubProvider:
            raise RuntimeError("synthetic construction failure")

        service = CachedReferenceRateService(failing_factory, ttl_seconds=60)

        with self.assertRaisesRegex(RuntimeError, "synthetic construction failure"):
            service.latest_reference_rate("USD")

        health = service.health_snapshot()
        self.assertEqual(health.status, "LAST_ATTEMPT_FAILED")
        self.assertEqual(health.upstream_attempt_count, 1)
        self.assertEqual(health.failure_count, 1)
        self.assertEqual(health.success_count, 0)

    def test_concurrent_cache_misses_produce_one_upstream_attempt(self) -> None:
        provider = StubProvider()
        service = CachedReferenceRateService(lambda: provider, ttl_seconds=60)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(service.latest_reference_rate, ["USD"] * 16))

        self.assertEqual(provider.calls, 1)
        self.assertTrue(all(result is results[0] for result in results))
        health = service.health_snapshot()
        self.assertEqual(health.upstream_attempt_count, 1)
        self.assertEqual(health.success_count, 1)
        self.assertEqual(health.cache_hit_count, 15)

    def test_health_rejects_a_naive_observation_clock(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            CachedReferenceRateService(
                StubProvider,
                ttl_seconds=60,
                observed_clock=lambda: datetime(2026, 9, 1, 8),
            )

    def test_configured_ttl_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(ecb_cache_ttl_seconds=59)
        with self.assertRaises(ValidationError):
            Settings(ecb_cache_ttl_seconds=86_401)


if __name__ == "__main__":
    unittest.main()
