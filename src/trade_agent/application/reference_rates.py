from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from trade_agent.domain.errors import PublicInputError
from trade_agent.domain.models import FXRate


class ReferenceRateProvider(Protocol):
    def latest_reference_rate(self, quote_currency: str) -> FXRate: ...


class ProviderRuntimeHealthStatus(StrEnum):
    DISABLED = "DISABLED"
    NOT_OBSERVED = "NOT_OBSERVED"
    LAST_ATTEMPT_SUCCEEDED = "LAST_ATTEMPT_SUCCEEDED"
    LAST_ATTEMPT_FAILED = "LAST_ATTEMPT_FAILED"


@dataclass(frozen=True, slots=True)
class ProviderRuntimeHealthSnapshot:
    status: ProviderRuntimeHealthStatus
    observed_since: datetime
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    upstream_attempt_count: int
    success_count: int
    failure_count: int
    consecutive_failure_count: int
    cache_hit_count: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CachedReferenceRateService:
    def __init__(
        self,
        provider_factory: Callable[[], ReferenceRateProvider],
        *,
        ttl_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        observed_clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("reference-rate cache TTL must be positive")
        self._provider_factory = provider_factory
        self._provider: ReferenceRateProvider | None = None
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._observed_clock = observed_clock
        self._observed_since = self._read_observed_clock()
        self._cache: dict[str, tuple[float, FXRate]] = {}
        self._lock = threading.Lock()
        self._last_attempt_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._upstream_attempt_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._consecutive_failure_count = 0
        self._cache_hit_count = 0

    def latest_reference_rate(self, quote_currency: str) -> FXRate:
        currency = quote_currency.strip().upper()
        if currency == "EUR" or len(currency) != 3 or not currency.isalpha():
            raise PublicInputError("quote currency must be a non-EUR three-letter code")
        with self._lock:
            now = self._clock()
            cached = self._cache.get(currency)
            if cached is not None and cached[0] > now:
                self._cache_hit_count += 1
                return cached[1]
            attempted_at = self._read_observed_clock()
            self._last_attempt_at = attempted_at
            self._upstream_attempt_count += 1
            try:
                if self._provider is None:
                    self._provider = self._provider_factory()
                rate = self._provider.latest_reference_rate(currency)
            except Exception:
                self._last_failure_at = attempted_at
                self._failure_count += 1
                self._consecutive_failure_count += 1
                raise
            self._last_success_at = attempted_at
            self._success_count += 1
            self._consecutive_failure_count = 0
            self._cache[currency] = (self._clock() + self._ttl_seconds, rate)
            return rate

    def health_snapshot(self) -> ProviderRuntimeHealthSnapshot:
        with self._lock:
            if self._last_attempt_at is None:
                status = ProviderRuntimeHealthStatus.NOT_OBSERVED
            elif self._consecutive_failure_count:
                status = ProviderRuntimeHealthStatus.LAST_ATTEMPT_FAILED
            else:
                status = ProviderRuntimeHealthStatus.LAST_ATTEMPT_SUCCEEDED
            return ProviderRuntimeHealthSnapshot(
                status=status,
                observed_since=self._observed_since,
                last_attempt_at=self._last_attempt_at,
                last_success_at=self._last_success_at,
                last_failure_at=self._last_failure_at,
                upstream_attempt_count=self._upstream_attempt_count,
                success_count=self._success_count,
                failure_count=self._failure_count,
                consecutive_failure_count=self._consecutive_failure_count,
                cache_hit_count=self._cache_hit_count,
            )

    def _read_observed_clock(self) -> datetime:
        observed_at = self._observed_clock()
        if observed_at.tzinfo is None:
            raise ValueError("provider observation clock must be timezone-aware")
        return observed_at.astimezone(UTC)
