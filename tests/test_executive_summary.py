import unittest
from dataclasses import replace
from decimal import Decimal

from trade_agent.application.executive_summary import (
    ExecutiveDecisionSummary,
    ExecutiveSupplierCandidate,
    build_executive_summary,
)
from trade_agent.domain.errors import PublicInputError


def candidate(observation_id: str = "offer-1") -> ExecutiveSupplierCandidate:
    return ExecutiveSupplierCandidate(
        observation_id=observation_id,
        supplier_name="Supplier Fixture",
        original_amount=Decimal("5"),
        original_currency="USD",
        normalized_amount=Decimal("500"),
        normalized_currency="IRR",
        total_score=75,
        source_url="https://example.com/fixture",
        evidence_classification="FACT",
        evidence_confidence="HIGH",
    )


def summary(
    *,
    validation_disposition: str = "NEEDS_VERIFICATION",
    confidence_score: int = 70,
    leading_supplier_candidates: tuple[ExecutiveSupplierCandidate, ...] | None = None,
) -> ExecutiveDecisionSummary:
    return build_executive_summary(
        validation_disposition=validation_disposition,
        confidence_score=confidence_score,
        confidence_label="MEDIUM",
        base_landed_cost_per_unit=Decimal("630"),
        base_landed_cost_currency="IRR",
        leading_supplier_candidates=(
            (candidate(),)
            if leading_supplier_candidates is None
            else leading_supplier_candidates
        ),
        data_gap_status="GAPS_REQUIRE_VERIFICATION",
        data_gap_issue_count=3,
        declared_unknown_count=1,
    )


class ExecutiveSummaryTests(unittest.TestCase):
    def test_verification_summary_withholds_unapproved_market_comparison(self) -> None:
        result = summary()

        self.assertEqual(result.decision_status, "VERIFICATION_REQUIRED")
        self.assertEqual(result.recommendation_code, "VERIFY_GAPS_BEFORE_PURCHASE")
        self.assertEqual(result.supplier_candidate_status, "SINGLE_UNVERIFIED_CANDIDATE")
        self.assertEqual(result.iran_market_benchmark_status, "WITHHELD_NO_APPROVED_BENCHMARK")
        self.assertIsNone(result.iran_market_unit_price)
        self.assertIsNone(result.potential_gross_spread_per_unit)
        self.assertIsNone(result.potential_gross_spread_percent)

    def test_errors_take_precedence_and_tied_candidates_are_deterministic(self) -> None:
        second = replace(
            candidate("offer-2"),
            supplier_name="Another Fixture",
            normalized_amount=Decimal("490"),
        )
        result = summary(
            validation_disposition="NEEDS_HUMAN_REVIEW",
            leading_supplier_candidates=(candidate(), second),
        )

        self.assertEqual(result.decision_status, "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(result.recommendation_code, "RESOLVE_ERRORS_BEFORE_PURCHASE")
        self.assertEqual(
            result.supplier_candidate_status,
            "MULTIPLE_LEADING_UNVERIFIED_CANDIDATES",
        )
        self.assertEqual(
            [item.observation_id for item in result.leading_supplier_candidates],
            ["offer-2", "offer-1"],
        )

    def test_no_candidate_and_invalid_inputs_are_explicit(self) -> None:
        result = summary(
            validation_disposition="PASSED",
            leading_supplier_candidates=(),
        )
        self.assertEqual(result.decision_status, "COMMERCIAL_REVIEW_REQUIRED")
        self.assertEqual(result.supplier_candidate_status, "NO_RANKED_SUPPLIER_CANDIDATE")

        with self.assertRaisesRegex(PublicInputError, "between 0 and 100"):
            summary(confidence_score=101)
        with self.assertRaisesRegex(PublicInputError, "unsupported"):
            summary(validation_disposition="UNKNOWN")


if __name__ == "__main__":
    unittest.main()
