import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from trade_agent.application.matching import match_research_case
from trade_agent.application.ranking import rank_supplier_offers
from trade_agent.application.research import execute_research_case
from trade_agent.application.validation import ValidationDisposition
from trade_agent.domain.models import Confidence, EvidenceClass, Money
from trade_agent.providers.evidence_bundle import load_evidence_bundle


class SupplierOfferRankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = load_evidence_bundle(Path("examples/demo_case.json"))
        self.observation = self.case.observations[0]

    def test_stronger_evidence_can_outweigh_small_price_difference(self) -> None:
        stronger_evidence = replace(
            self.observation.evidence,
            classification=EvidenceClass.FACT,
            confidence=Confidence.HIGH,
            raw_value="Synthetic test value: 6 USD",
        )
        stronger_offer = replace(
            self.observation,
            observation_id="price-stronger-evidence",
            supplier_name="Verified Fixture Supplier",
            unit_price=Money(Decimal("6"), "USD"),
            evidence=stronger_evidence,
        )
        case = replace(self.case, observations=(self.observation, stronger_offer))

        rankings = rank_supplier_offers(case, match_research_case(case))
        by_id = {ranking.observation_id: ranking for ranking in rankings}

        self.assertEqual(by_id["price-stronger-evidence"].rank, 1)
        self.assertEqual(by_id["demo-price-1"].rank, 2)
        self.assertEqual(
            by_id["price-stronger-evidence"].normalized_unit_price,
            Money(Decimal("600.00"), "IRR"),
        )
        self.assertGreater(
            by_id["price-stronger-evidence"].total_score,
            by_id["demo-price-1"].total_score,
        )

    def test_offer_below_moq_is_not_ranked(self) -> None:
        observation = replace(
            self.observation,
            minimum_order_quantity=self.case.quantity + 1,
        )
        case = replace(self.case, observations=(observation,))

        ranking = rank_supplier_offers(case, match_research_case(case))[0]

        self.assertFalse(ranking.eligible_for_quantity)
        self.assertFalse(ranking.rankable)
        self.assertIsNone(ranking.rank)
        self.assertEqual(ranking.component_scores["quantity_fit"], 0)

        result = execute_research_case(case)
        self.assertIn(
            "OFFER_BELOW_MINIMUM_ORDER",
            {issue.code for issue in result.validation.issues},
        )

    def test_missing_fx_path_keeps_original_offer_but_prevents_ranking(self) -> None:
        observation = replace(
            self.observation,
            unit_price=Money(Decimal("5"), "EUR"),
        )
        case = replace(self.case, observations=(observation,))

        ranking = rank_supplier_offers(case, match_research_case(case))[0]

        self.assertIsNone(ranking.normalized_unit_price)
        self.assertFalse(ranking.rankable)
        self.assertIn("comparable_fx_rate", ranking.unknown_factors)

        result = execute_research_case(case)
        self.assertEqual(
            result.validation.disposition,
            ValidationDisposition.NEEDS_HUMAN_REVIEW,
        )
        self.assertIn(
            "UNCONVERTIBLE_OFFER_PRICE",
            {issue.code for issue in result.validation.issues},
        )

    def test_equal_offers_receive_the_same_dense_rank(self) -> None:
        second = replace(
            self.observation,
            observation_id="same-price-2",
            supplier_name="Second Fixture Supplier",
        )
        case = replace(self.case, observations=(self.observation, second))

        rankings = rank_supplier_offers(case, match_research_case(case))

        self.assertEqual([ranking.rank for ranking in rankings], [1, 1])

    def test_missing_supplier_identity_requires_human_review(self) -> None:
        anonymous = replace(self.observation, supplier_name=None)

        result = execute_research_case(replace(self.case, observations=(anonymous,)))

        self.assertEqual(
            result.validation.disposition,
            ValidationDisposition.NEEDS_HUMAN_REVIEW,
        )
        self.assertIn(
            "MISSING_SUPPLIER_IDENTITY",
            {issue.code for issue in result.validation.issues},
        )
        self.assertFalse(result.supplier_rankings[0].rankable)

    def test_single_rankable_offer_receives_neutral_price_score(self) -> None:
        ranking = rank_supplier_offers(
            self.case,
            match_research_case(self.case),
        )[0]

        self.assertEqual(ranking.rank, 1)
        self.assertEqual(ranking.component_scores["price_competitiveness"], 12)

    def test_incoterm_completeness_scores_code_place_and_version_separately(self) -> None:
        complete = rank_supplier_offers(
            self.case,
            match_research_case(self.case),
        )[0]
        incomplete_observation = replace(
            self.observation,
            incoterm_named_place=None,
            incoterm_version=None,
        )
        incomplete_case = replace(
            self.case,
            observations=(incomplete_observation,),
        )
        incomplete = rank_supplier_offers(
            incomplete_case,
            match_research_case(incomplete_case),
        )[0]

        self.assertEqual(
            complete.component_scores["commercial_completeness"]
            - incomplete.component_scores["commercial_completeness"],
            2,
        )
        self.assertIn("incoterm_named_place", incomplete.unknown_factors)
        self.assertIn("incoterm_version", incomplete.unknown_factors)


if __name__ == "__main__":
    unittest.main()
