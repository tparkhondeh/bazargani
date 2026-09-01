import unittest
from dataclasses import replace
from pathlib import Path

from trade_agent.application.matching import (
    match_price_observation,
    normalize_product_text,
)
from trade_agent.application.research import execute_research_case
from trade_agent.application.validation import ValidationDisposition
from trade_agent.domain.models import ProductMatchClass
from trade_agent.providers.evidence_bundle import load_evidence_bundle


class ProductMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = load_evidence_bundle(Path("examples/demo_case.json"))
        self.observation = self.case.observations[0]

    def test_persian_and_arabic_characters_and_digits_normalize_deterministically(self) -> None:
        self.assertEqual(normalize_product_text("پمپ آب مدل ۱۲۳"), "پمپ اب مدل 123")
        self.assertEqual(normalize_product_text("كالاى نمونه"), "کالای نمونه")

    def test_exact_variant_requires_all_requested_attributes(self) -> None:
        match = match_price_observation(self.case, self.observation)

        self.assertEqual(match.classification, ProductMatchClass.EXACT_VARIANT)
        self.assertEqual(match.score, 100)
        self.assertEqual(match.matched_attributes, ("variant",))
        self.assertEqual(match.conflicting_attributes, ())

    def test_exact_product_exposes_missing_variant_attributes(self) -> None:
        observation = replace(
            self.observation,
            product_variant=None,
            product_attributes={},
        )

        match = match_price_observation(self.case, observation)

        self.assertEqual(match.classification, ProductMatchClass.EXACT_PRODUCT)
        self.assertEqual(match.missing_attributes, ("variant",))
        self.assertLess(match.score, 100)

        result = execute_research_case(replace(self.case, observations=(observation,)))
        self.assertIn(
            "UNVERIFIED_PRODUCT_VARIANT",
            {issue.code for issue in result.validation.issues},
        )

    def test_comparable_product_uses_name_and_attribute_features(self) -> None:
        case = replace(
            self.case,
            product_name="پمپ آب صنعتی",
            product_attributes={"voltage": "220V"},
        )
        observation = replace(
            self.observation,
            product_name="پمپ آب",
            product_variant=None,
            product_attributes={"voltage": "۲۲۰v"},
        )

        match = match_price_observation(case, observation)

        self.assertEqual(match.classification, ProductMatchClass.COMPARABLE)
        self.assertEqual(match.matched_attributes, ("voltage",))

    def test_conflicting_variant_escalates_validation_to_human_review(self) -> None:
        observation = replace(
            self.observation,
            product_variant=None,
            product_attributes={"variant": "REAL"},
        )
        result = execute_research_case(
            replace(self.case, observations=(observation,))
        )

        self.assertEqual(
            result.product_matches[0].classification,
            ProductMatchClass.SIMILAR,
        )
        self.assertEqual(
            result.validation.disposition,
            ValidationDisposition.NEEDS_HUMAN_REVIEW,
        )
        self.assertIn(
            "PRODUCT_ATTRIBUTE_CONFLICT",
            {issue.code for issue in result.validation.issues},
        )

    def test_unrelated_product_is_explicitly_a_substitute(self) -> None:
        observation = replace(
            self.observation,
            product_name="کابل شبکه",
            product_variant=None,
            product_attributes={},
        )

        match = match_price_observation(self.case, observation)

        self.assertEqual(match.classification, ProductMatchClass.SUBSTITUTE)
        self.assertEqual(match.score, 0)

    def test_generic_matching_attribute_cannot_hide_an_unrelated_product(self) -> None:
        case = replace(self.case, product_attributes={"voltage": "220V"})
        observation = replace(
            self.observation,
            product_name="کابل شبکه",
            product_variant=None,
            product_attributes={"voltage": "220V"},
        )

        match = match_price_observation(case, observation)

        self.assertEqual(match.classification, ProductMatchClass.SUBSTITUTE)


if __name__ == "__main__":
    unittest.main()
