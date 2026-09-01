import unittest
from decimal import Decimal

from trade_agent.application.sensitivity import (
    ScenarioCostPoint,
    analyze_scenario_sensitivity,
)


def point(
    name: str,
    amount: str,
    *,
    quantity: int = 10,
    currency: str = "IRR",
) -> ScenarioCostPoint:
    return ScenarioCostPoint(name, quantity, currency, Decimal(amount))


class ScenarioSensitivityTests(unittest.TestCase):
    def test_comparable_scenarios_have_exact_decimal_deltas(self) -> None:
        result = analyze_scenario_sensitivity(
            (
                point("OPTIMISTIC", "576.30"),
                point("BASE", "630.00"),
                point("CONSERVATIVE", "737.00"),
            )
        )

        self.assertEqual(result.status, "COMPARABLE")
        self.assertEqual(result.optimistic_delta_from_base, Decimal("-53.70"))
        self.assertEqual(result.optimistic_delta_percent, Decimal("-8.52"))
        self.assertEqual(result.conservative_delta_from_base, Decimal("107.00"))
        self.assertEqual(result.conservative_delta_percent, Decimal("16.98"))
        self.assertEqual(result.range_per_unit, Decimal("160.70"))
        self.assertEqual(result.range_percent_of_base, Decimal("25.51"))

    def test_mixed_quantity_or_currency_never_produces_comparison_numbers(self) -> None:
        result = analyze_scenario_sensitivity(
            (
                point("OPTIMISTIC", "5", quantity=100),
                point("BASE", "4", quantity=500),
                point("CONSERVATIVE", "3", quantity=500, currency="USD"),
            )
        )

        self.assertEqual(result.status, "MIXED_BASIS")
        self.assertIsNone(result.base_per_unit)
        self.assertIsNone(result.range_per_unit)
        self.assertIsNone(result.range_percent_of_base)

    def test_zero_base_retains_amounts_but_not_undefined_percentages(self) -> None:
        result = analyze_scenario_sensitivity(
            (
                point("OPTIMISTIC", "0"),
                point("BASE", "0"),
                point("CONSERVATIVE", "1"),
            )
        )

        self.assertEqual(result.status, "ZERO_BASE")
        self.assertEqual(result.range_per_unit, Decimal("1"))
        self.assertIsNone(result.optimistic_delta_percent)
        self.assertIsNone(result.conservative_delta_percent)
        self.assertIsNone(result.range_percent_of_base)

    def test_missing_or_duplicate_named_scenario_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            analyze_scenario_sensitivity(
                (
                    point("OPTIMISTIC", "1"),
                    point("BASE", "1"),
                    point("BASE", "1"),
                )
            )


if __name__ == "__main__":
    unittest.main()
