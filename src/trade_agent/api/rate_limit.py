from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("API request rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


@dataclass(slots=True)
class _Window:
    started_at: float
    request_count: int


class TenantRateLimiter:
    """Thread-safe, per-process fixed-window limiter keyed by resolved tenant."""

    def __init__(
        self,
        *,
        requests_per_window: int,
        window_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if requests_per_window <= 0:
            raise ValueError("requests_per_window must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._requests_per_window = requests_per_window
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    def check(self, tenant_id: str) -> None:
        now = self._clock()
        with self._lock:
            window = self._windows.get(tenant_id)
            if window is None or now - window.started_at >= self._window_seconds:
                self._windows[tenant_id] = _Window(started_at=now, request_count=1)
                return
            if window.request_count < self._requests_per_window:
                window.request_count += 1
                return
            retry_after = max(1, ceil(self._window_seconds - (now - window.started_at)))
            raise RateLimitExceeded(retry_after)
