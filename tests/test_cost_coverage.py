import unittest

from trade_agent.application.cost_coverage import (
    CostCoveragePoint,
    ScenarioCostCoverageInput,
    analyze_trade_cost_coverage,
)
from trade_agent.domain.errors import PublicInputError


class TradeCostCoverageTests(unittest.TestCase):
    def test_recorded_reference_and_custom_components_remain_distinct(self) -> None:
        result = analyze_trade_cost_coverage(
            (
                ScenarioCostCoverageInput(
                    name="BASE",
                    components=(
                        CostCoveragePoint("product_cost", "DERIVED_CALCULATION", False),
                        CostCoveragePoint("freight", "ASSUMPTION", False),
                        CostCoveragePoint("local_special_fee", "ESTIMATE", True),
                    ),
                ),
            )
        )

        coverage = result.scenarios[0]
        self.assertEqual(coverage.recorded_component_count, 3)
        self.assertEqual(
            coverage.recognized_reference_codes,
            ("product_cost", "freight"),
        )
        self.assertEqual(coverage.unclassified_component_codes, ("local_special_fee",))
        self.assertEqual(coverage.zero_amount_codes, ("local_special_fee",))
        self.assertIn("insurance", coverage.unrecorded_reference_codes)
        self.assertEqual(coverage.estimate_count, 1)
        self.assertEqual(coverage.assumption_count, 1)
        self.assertEqual(coverage.derived_calculation_count, 1)

    def test_scenarios_use_semantic_order_and_empty_status_is_explicit(self) -> None:
        point = CostCoveragePoint("product_cost", "FACT", False)
        result = analyze_trade_cost_coverage(
            (
                ScenarioCostCoverageInput("CONSERVATIVE", (point,)),
                ScenarioCostCoverageInput("OPTIMISTIC", (point,)),
                ScenarioCostCoverageInput("BASE", (point,)),
            )
        )

        self.assertEqual(
            [scenario.name for scenario in result.scenarios],
            ["OPTIMISTIC", "BASE", "CONSERVATIVE"],
        )
        self.assertEqual(analyze_trade_cost_coverage(()).status, "NO_COST_SCENARIOS")

    def test_duplicate_scenarios_and_unknown_evidence_classes_fail_closed(self) -> None:
        empty = ScenarioCostCoverageInput("BASE", ())
        with self.assertRaisesRegex(PublicInputError, "must be unique"):
            analyze_trade_cost_coverage((empty, empty))

        invalid = ScenarioCostCoverageInput(
            "BASE",
            (CostCoveragePoint("fee", "UNKNOWN", False),),
        )
        with self.assertRaisesRegex(PublicInputError, "evidence class"):
            analyze_trade_cost_coverage((invalid,))


if __name__ == "__main__":
    unittest.main()
