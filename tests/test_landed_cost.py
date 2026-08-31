import unittest
from datetime import UTC, datetime
from decimal import Decimal

from trade_agent.calculation.landed_cost import calculate_landed_cost, convert
from trade_agent.domain.models import (
    Confidence,
    CostInput,
    Evidence,
    EvidenceClass,
    FXRate,
    Money,
    ScenarioInput,
    ScenarioName,
)


def evidence() -> Evidence:
    return Evidence(
        EvidenceClass.FACT,
        "Test source",
        "https://example.com/fx",
        datetime(2026, 8, 31, tzinfo=UTC),
        "1 USD = 100 IRR",
        Confidence.HIGH,
    )


def rates() -> tuple[FXRate, ...]:
    return (
        FXRate("USD", "IRR", Decimal("100"), evidence(), "TEST"),
        FXRate("CNY", "USD", Decimal("0.14"), evidence(), "TEST"),
    )


class LandedCostTests(unittest.TestCase):
    def test_convert_uses_reproducible_multihop_rate(self) -> None:
        self.assertEqual(
            convert(Money(Decimal("10"), "CNY"), "IRR", rates()), Money(Decimal("140.00"), "IRR")
        )

    def test_convert_rejects_missing_fx_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "no FX path"):
            convert(Money(Decimal("1"), "EUR"), "IRR", rates())

    def test_golden_landed_cost_scenario(self) -> None:
        scenario = ScenarioInput(
            name=ScenarioName.BASE,
            quantity=10,
            purchase_unit_price=Money(Decimal("5"), "USD"),
            costs=(
                CostInput(
                    "freight", "حمل", Money(Decimal("1000"), "IRR"), "TOTAL", EvidenceClass.ESTIMATE
                ),
                CostInput(
                    "clearance",
                    "ترخیص",
                    Money(Decimal("10"), "IRR"),
                    "PER_UNIT",
                    EvidenceClass.ASSUMPTION,
                ),
            ),
            target_currency="IRR",
            fx_rates=rates(),
            purchase_price_multiplier=Decimal("1.10"),
            cost_multiplier=Decimal("1.20"),
            unexpected_cost_rate=Decimal("0.05"),
        )
        result = calculate_landed_cost(scenario)
        self.assertEqual(result.total, Money(Decimal("7161.00"), "IRR"))
        self.assertEqual(result.per_unit, Money(Decimal("716.10"), "IRR"))
        self.assertEqual(
            [component.code for component in result.components],
            ["product_cost", "freight", "clearance", "unexpected_cost"],
        )


if __name__ == "__main__":
    unittest.main()
