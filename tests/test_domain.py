import unittest
from datetime import UTC, datetime
from decimal import Decimal

from trade_agent.domain.models import (
    Confidence,
    Evidence,
    EvidenceClass,
    Money,
    PriceObservation,
)


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

    def test_price_observation_requires_explicit_unit(self) -> None:
        evidence = Evidence(
            EvidenceClass.FACT,
            "source",
            "https://example.com/item",
            datetime(2026, 8, 31, tzinfo=UTC),
            "10 USD",
            Confidence.HIGH,
        )
        with self.assertRaisesRegex(ValueError, "unit"):
            PriceObservation(
                observation_id="price-1",
                product_name="item",
                unit_price=Money(Decimal("10"), "USD"),
                quantity=1,
                unit=" ",
                evidence=evidence,
            )


if __name__ == "__main__":
    unittest.main()
