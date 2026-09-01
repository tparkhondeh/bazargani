import unittest
from dataclasses import replace

from trade_agent.application.offer_terms_coverage import (
    OfferTermsPoint,
    summarize_offer_terms_coverage,
)
from trade_agent.domain.errors import PublicInputError


def point(observation_id: str, *, complete: bool) -> OfferTermsPoint:
    return OfferTermsPoint(
        observation_id=observation_id,
        supplier_name="Supplier Fixture" if complete else " ",
        minimum_order_quantity=10 if complete else None,
        product_variant="Variant" if complete else None,
        product_attributes={},
        incoterm="FOB" if complete else None,
        incoterm_named_place="Fixture Port" if complete else None,
        incoterm_version="2020" if complete else None,
        rankable=complete,
        ranking_unknown_factors=("payment_terms", "payment_terms"),
    )


class OfferTermsCoverageTests(unittest.TestCase):
    def test_declared_and_missing_fields_are_exact_and_ordered(self) -> None:
        result = summarize_offer_terms_coverage(
            (point("missing", complete=False), point("complete", complete=True))
        )

        self.assertEqual(result.status, "RECORDED_CORE_TERM_GAPS")
        self.assertEqual(
            [offer.observation_id for offer in result.offers],
            ["complete", "missing"],
        )
        complete, missing = result.offers
        self.assertEqual(
            complete.declared_fields,
            result.recorded_core_term_fields,
        )
        self.assertEqual(complete.missing_recorded_fields, ())
        self.assertEqual(complete.declared_recorded_field_count, 6)
        self.assertIsNone(missing.supplier_name)
        self.assertEqual(missing.declared_fields, ())
        self.assertEqual(
            missing.missing_recorded_fields,
            result.recorded_core_term_fields,
        )
        self.assertEqual(missing.ranking_unknown_factors, ("payment_terms",))
        self.assertIn("quote_valid_until", result.uncaptured_commercial_term_fields)

    def test_empty_and_all_present_statuses_are_distinct(self) -> None:
        self.assertEqual(summarize_offer_terms_coverage(()).status, "NO_OFFERS")
        attributes_only = replace(
            point("complete", complete=True),
            product_variant=None,
            product_attributes={"grade": "A"},
        )
        self.assertEqual(
            summarize_offer_terms_coverage((attributes_only,)).status,
            "RECORDED_CORE_TERMS_PRESENT",
        )

    def test_duplicate_observation_ids_fail_closed(self) -> None:
        duplicate = point("duplicate", complete=True)
        with self.assertRaisesRegex(PublicInputError, "must be unique"):
            summarize_offer_terms_coverage((duplicate, duplicate))


if __name__ == "__main__":
    unittest.main()
