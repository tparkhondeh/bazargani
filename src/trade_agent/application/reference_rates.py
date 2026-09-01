from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol

from trade_agent.domain.models import FXRate


class ReferenceRateProvider(Protocol):
    def latest_reference_rate(self, quote_currency: str) -> FXRate: ...


class CachedReferenceRateService:
    def __init__(
        self,
        provider_factory: Callable[[], ReferenceRateProvider],
        *,
        ttl_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("reference-rate cache TTL must be positive")
        self._provider_factory = provider_factory
        self._provider: ReferenceRateProvider | None = None
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, FXRate]] = {}
        self._lock = threading.Lock()

    def latest_reference_rate(self, quote_currency: str) -> FXRate:
        currency = quote_currency.strip().upper()
        with self._lock:
            now = self._clock()
            cached = self._cache.get(currency)
            if cached is not None and cached[0] > now:
                return cached[1]
            if self._provider is None:
                self._provider = self._provider_factory()
            rate = self._provider.latest_reference_rate(currency)
            self._cache[currency] = (self._clock() + self._ttl_seconds, rate)
            return rate
