from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx


class UnsafeUrlError(ValueError):
    pass


class ResponseTooLargeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    body: bytes
    content_type: str


Resolver = Callable[[str], Collection[str]]


def system_resolver(hostname: str) -> Collection[str]:
    return {str(item[4][0]) for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}


def validate_public_https_url(
    url: str, *, allowed_hosts: Collection[str], resolver: Resolver = system_resolver
) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise UnsafeUrlError("only HTTPS URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL credentials are forbidden")
    if parsed.fragment:
        raise UnsafeUrlError("URL fragments are forbidden")
    if parsed.port not in (None, 443):
        raise UnsafeUrlError("only port 443 is allowed")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    normalized_hosts = {host.rstrip(".").lower() for host in allowed_hosts}
    if hostname not in normalized_hosts:
        raise UnsafeUrlError("host is not allowlisted")
    addresses = resolver(hostname)
    if not addresses:
        raise UnsafeUrlError("host did not resolve")
    for address in addresses:
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeUrlError("resolver returned an invalid IP address") from exc
        if not parsed_address.is_global:
            raise UnsafeUrlError("host resolves to a non-public IP address")


class SafeHttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: Collection[str],
        resolver: Resolver = system_resolver,
        client: httpx.Client | None = None,
        max_response_bytes: int = 2_000_000,
        max_attempts: int = 3,
        backoff_seconds: float = 0.1,
    ) -> None:
        if max_response_bytes <= 0 or max_attempts <= 0:
            raise ValueError("limits must be positive")
        self._allowed_hosts = frozenset(allowed_hosts)
        self._resolver = resolver
        self._max_response_bytes = max_response_bytes
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "bazargani-trade-agent/0.3 (+source-backed-research)"},
        )

    def get(self, url: str) -> FetchResult:
        validate_public_https_url(url, allowed_hosts=self._allowed_hosts, resolver=self._resolver)
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                with self._client.stream("GET", url, headers={"Accept": "text/csv"}) as response:
                    if 300 <= response.status_code < 400:
                        raise UnsafeUrlError("redirects are forbidden")
                    if response.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            "upstream server error", request=response.request, response=response
                        )
                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > self._max_response_bytes:
                        raise ResponseTooLargeError("declared response is too large")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self._max_response_bytes:
                            raise ResponseTooLargeError("response exceeded byte limit")
                        chunks.append(chunk)
                    return FetchResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        body=b"".join(chunks),
                        content_type=response.headers.get("content-type", ""),
                    )
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    time.sleep(self._backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error
