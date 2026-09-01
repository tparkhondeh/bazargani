import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trade_agent.application.validation import (
    ValidationDisposition,
    validate_research_case,
)
from trade_agent.domain.models import Confidence, EvidenceClass, Money, ResearchCase
from trade_agent.providers.evidence_bundle import load_evidence_bundle

EVALUATED_AT = datetime(2026, 8, 31, 12, tzinfo=UTC)


def demo_case() -> ResearchCase:
    return load_evidence_bundle(Path("examples/demo_case.json"))


class ValidationTests(unittest.TestCase):
    def test_clean_fact_backed_case_passes_with_full_confidence(self) -> None:
        case = demo_case()
        observation = case.observations[0]
        factual_observation = replace(
            observation,
            evidence=replace(
                observation.evidence,
                classification=EvidenceClass.FACT,
                confidence=Confidence.HIGH,
            ),
        )
        rates = tuple(
            replace(
                rate,
                evidence=replace(
                    rate.evidence,
                    classification=EvidenceClass.FACT,
                    confidence=Confidence.HIGH,
                ),
            )
            for rate in case.scenarios[0].fx_rates
        )
        scenarios = tuple(
            replace(
                scenario,
                fx_rates=rates,
                costs=tuple(
                    replace(cost, evidence_class=EvidenceClass.FACT)
                    for cost in scenario.costs
                ),
            )
            for scenario in case.scenarios
        )
        clean_case = replace(
            case,
            observations=(factual_observation,),
            scenarios=scenarios,
            assumptions=(),
            unknowns=(),
        )

        _, validation = validate_research_case(clean_case, evaluated_at=EVALUATED_AT)

        self.assertEqual(validation.disposition, ValidationDisposition.PASSED)
        self.assertEqual(validation.confidence_score, 100)
        self.assertEqual(validation.confidence_label, Confidence.HIGH)
        self.assertEqual(validation.issues, ())

    def test_exact_duplicate_is_removed_and_explained(self) -> None:
        case = demo_case()
        duplicate = replace(case.observations[0], observation_id="demo-price-copy")
        duplicated_case = replace(case, observations=(*case.observations, duplicate))

        cleaned, validation = validate_research_case(
            duplicated_case, evaluated_at=EVALUATED_AT
        )

        self.assertEqual(len(cleaned.observations), 1)
        duplicate_issue = next(
            issue
            for issue in validation.issues
            if issue.code == "DUPLICATE_PRICE_OBSERVATION"
        )
        self.assertEqual(duplicate_issue.subject_id, "demo-price-copy")
        self.assertEqual(duplicate_issue.details, {"duplicate_of": "demo-price-1"})

    def test_incomplete_incoterm_terms_require_verification(self) -> None:
        case = demo_case()
        observation = replace(
            case.observations[0],
            incoterm_named_place=None,
            incoterm_version=None,
        )

        _, validation = validate_research_case(
            replace(case, observations=(observation,)),
            evaluated_at=EVALUATED_AT,
        )

        issue = next(
            item
            for item in validation.issues
            if item.code == "INCOMPLETE_INCOTERM_TERMS"
        )
        self.assertEqual(
            issue.details,
            {"missing_fields": ["incoterm_named_place", "incoterm_version"]},
        )
        self.assertEqual(validation.disposition, ValidationDisposition.NEEDS_VERIFICATION)

    def test_incoterm_place_and_version_participate_in_deduplication(self) -> None:
        case = demo_case()
        original = case.observations[0]
        different_place = replace(
            original,
            observation_id="different-incoterm-place",
            incoterm_named_place="Another Fixture Gate",
        )

        cleaned, validation = validate_research_case(
            replace(case, observations=(original, different_place)),
            evaluated_at=EVALUATED_AT,
        )

        self.assertEqual(len(cleaned.observations), 2)
        self.assertNotIn(
            "DUPLICATE_PRICE_OBSERVATION",
            {issue.code for issue in validation.issues},
        )

    def test_stale_and_outlier_prices_require_verification(self) -> None:
        case = demo_case()
        original = case.observations[0]
        stale_evidence = replace(
            original.evidence,
            retrieved_at=EVALUATED_AT - timedelta(days=31),
            classification=EvidenceClass.FACT,
            confidence=Confidence.HIGH,
        )
        observations = (
            replace(original, observation_id="p1", unit_price=Money(Decimal("10"), "USD")),
            replace(original, observation_id="p2", unit_price=Money(Decimal("11"), "USD")),
            replace(
                original,
                observation_id="p3",
                unit_price=Money(Decimal("100"), "USD"),
                evidence=stale_evidence,
            ),
        )

        _, validation = validate_research_case(
            replace(case, observations=observations), evaluated_at=EVALUATED_AT
        )

        codes = {issue.code for issue in validation.issues}
        self.assertIn("STALE_EVIDENCE", codes)
        self.assertIn("PRICE_OUTLIER", codes)
        self.assertEqual(validation.disposition, ValidationDisposition.NEEDS_VERIFICATION)

    def test_material_conflicts_require_human_review(self) -> None:
        case = demo_case()
        invalid_observation = replace(
            case.observations[0],
            product_name="محصول دیگر",
            unit_price=Money(Decimal("0"), "USD"),
            minimum_order_quantity=case.quantity + 1,
        )

        _, validation = validate_research_case(
            replace(case, observations=(invalid_observation,)),
            evaluated_at=EVALUATED_AT,
        )

        codes = {issue.code for issue in validation.issues}
        self.assertTrue(
            {"ZERO_PRICE", "NO_QUANTITY_ELIGIBLE_PRICE"} <= codes
        )
        self.assertEqual(validation.disposition, ValidationDisposition.NEEDS_HUMAN_REVIEW)


if __name__ == "__main__":
    unittest.main()
