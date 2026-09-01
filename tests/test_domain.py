import unittest
from dataclasses import replace
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

    def test_price_observation_normalizes_structured_incoterm_terms(self) -> None:
        evidence = Evidence(
            EvidenceClass.FACT,
            "source",
            "https://example.com/item",
            datetime(2026, 8, 31, tzinfo=UTC),
            "10 USD",
            Confidence.HIGH,
        )
        observation = PriceObservation(
            observation_id="price-terms",
            product_name="item",
            unit_price=Money(Decimal("10"), "USD"),
            quantity=1,
            unit="device",
            evidence=evidence,
            incoterm=" fob ",
            incoterm_named_place=" Port of Fixture ",
            incoterm_version=" 2020 ",
        )

        self.assertEqual(observation.incoterm, "FOB")
        self.assertEqual(observation.incoterm_named_place, "Port of Fixture")
        self.assertEqual(observation.incoterm_version, "2020")

        with self.assertRaisesRegex(ValueError, "incoterm_named_place"):
            replace(observation, incoterm_named_place="x" * 301)
        with self.assertRaisesRegex(ValueError, "incoterm_named_place"):
            replace(observation, incoterm_named_place="Port\nforged")

    def test_price_observation_validates_payment_and_timing_terms(self) -> None:
        evidence = Evidence(
            EvidenceClass.FACT,
            "source",
            "https://example.com/item",
            datetime(2026, 8, 31, tzinfo=UTC),
            "10 USD",
            Confidence.HIGH,
        )
        observation = PriceObservation(
            observation_id="price-commercial-terms",
            product_name="item",
            unit_price=Money(Decimal("10"), "USD"),
            quantity=1,
            unit="device",
            evidence=evidence,
            payment_terms=" 30% advance ",
            payment_method=" Bank transfer ",
            quote_valid_until=datetime.fromisoformat("2099-12-31T20:00:00-04:00"),
            lead_time_days=30,
        )

        self.assertEqual(observation.payment_terms, "30% advance")
        self.assertEqual(observation.payment_method, "Bank transfer")
        self.assertEqual(
            observation.quote_valid_until,
            datetime(2100, 1, 1, tzinfo=UTC),
        )
        self.assertEqual(observation.lead_time_days, 30)

        for field, value in (
            ("payment_terms", "x" * 501),
            ("payment_method", "bank\ntransfer"),
            ("quote_valid_until", datetime(2099, 1, 1)),
            ("lead_time_days", 0),
            ("lead_time_days", True),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replace(observation, **{field: value})


if __name__ == "__main__":
    unittest.main()
