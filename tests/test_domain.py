import unittest
from datetime import datetime
from decimal import Decimal

from trade_agent.domain.models import Confidence, Evidence, EvidenceClass, Money


class DomainTests(unittest.TestCase):
    def test_money_normalizes_currency(self) -> None:
        self.assertEqual(Money(Decimal("12.34"), "usd").currency, "USD")

    def test_money_rejects_invalid_currency(self) -> None:
        for currency in ("US", "USDD", "12A"):
            with (
                self.subTest(currency=currency),
                self.assertRaisesRegex(ValueError, "three-letter"),
            ):
                Money(Decimal("1"), currency)

    def test_evidence_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Evidence(
                EvidenceClass.FACT,
                "source",
                "https://example.com/item",
                datetime(2026, 8, 31),
                "10 USD",
                Confidence.MEDIUM,
            )


if __name__ == "__main__":
    unittest.main()
