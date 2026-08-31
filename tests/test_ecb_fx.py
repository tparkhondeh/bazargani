import unittest
from decimal import Decimal

import httpx

from trade_agent.providers.ecb_fx import ECB_HOST, EcbFxProvider
from trade_agent.providers.http import SafeHttpClient

CSV_FIXTURE = b"""KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-08-28,1.1701
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-08-31,1.1802
"""


class EcbFxTests(unittest.TestCase):
    def test_parses_latest_reference_rate_with_provenance(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=CSV_FIXTURE, headers={"Content-Type": "text/csv"}
            )
        )
        safe_http = SafeHttpClient(
            allowed_hosts={ECB_HOST},
            resolver=lambda _: {"93.184.216.34"},
            client=httpx.Client(transport=transport),
        )

        rate = EcbFxProvider(safe_http).latest_reference_rate("usd")

        self.assertEqual(rate.base_currency, "EUR")
        self.assertEqual(rate.quote_currency, "USD")
        self.assertEqual(rate.rate, Decimal("1.1802"))
        self.assertEqual(rate.effective_at.isoformat(), "2026-08-31T00:00:00+00:00")
        self.assertEqual(rate.evidence.source_name, "European Central Bank Data Portal")
        self.assertIn("TIME_PERIOD", rate.evidence.raw_value)

    def test_rejects_eur_as_quote(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-EUR"):
            EcbFxProvider().latest_reference_rate("EUR")


if __name__ == "__main__":
    unittest.main()
