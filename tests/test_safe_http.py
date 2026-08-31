import unittest

import httpx

from trade_agent.providers.http import (
    ResponseTooLargeError,
    SafeHttpClient,
    UnsafeUrlError,
    validate_public_https_url,
)


def public_resolver(_: str) -> set[str]:
    return {"93.184.216.34"}


class SafeHttpTests(unittest.TestCase):
    def test_rejects_non_https_and_non_allowlisted_hosts(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url(
                "http://data-api.ecb.europa.eu/data",
                allowed_hosts={"data-api.ecb.europa.eu"},
                resolver=public_resolver,
            )
        with self.assertRaises(UnsafeUrlError):
            validate_public_https_url(
                "https://evil.example/data",
                allowed_hosts={"data-api.ecb.europa.eu"},
                resolver=public_resolver,
            )

    def test_rejects_private_resolution(self) -> None:
        with self.assertRaisesRegex(UnsafeUrlError, "non-public"):
            validate_public_https_url(
                "https://data-api.ecb.europa.eu/data",
                allowed_hosts={"data-api.ecb.europa.eu"},
                resolver=lambda _: {"127.0.0.1"},
            )

    def test_rejects_redirect_and_oversized_response(self) -> None:
        redirect_transport = httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "https://example.com"})
        )
        redirect_client = SafeHttpClient(
            allowed_hosts={"data-api.ecb.europa.eu"},
            resolver=public_resolver,
            client=httpx.Client(transport=redirect_transport),
            max_attempts=1,
        )
        with self.assertRaisesRegex(UnsafeUrlError, "redirect"):
            redirect_client.get("https://data-api.ecb.europa.eu/data")

        large_transport = httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 11)
        )
        large_client = SafeHttpClient(
            allowed_hosts={"data-api.ecb.europa.eu"},
            resolver=public_resolver,
            client=httpx.Client(transport=large_transport),
            max_response_bytes=10,
        )
        with self.assertRaises(ResponseTooLargeError):
            large_client.get("https://data-api.ecb.europa.eu/data")


if __name__ == "__main__":
    unittest.main()
