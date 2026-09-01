import unittest
from dataclasses import replace

from trade_agent.application.supplier_coverage import (
    SupplierEvidencePoint,
    summarize_supplier_coverage,
)


def point(observation_id: str, supplier_name: str | None) -> SupplierEvidencePoint:
    return SupplierEvidencePoint(
        observation_id=observation_id,
        supplier_name=supplier_name,
        source_url=f"https://example.com/{observation_id}",
        minimum_order_quantity=100,
        incoterm="FOB",
        rankable=True,
        unknown_factors=("certifications", "supplier_reliability"),
    )


class SupplierCoverageTests(unittest.TestCase):
    def test_offer_and_source_coverage_is_aggregated_without_verification_claim(self) -> None:
        first = point("offer-1", "Supplier A")
        second = replace(
            point("offer-2", "Supplier A"),
            source_url=first.source_url,
            minimum_order_quantity=None,
            incoterm=None,
            rankable=False,
            unknown_factors=("incoterm", "payment_terms"),
        )
        result = summarize_supplier_coverage((second, first))

        self.assertEqual(result.status, "SUPPLIER_EVIDENCE_COVERAGE")
        supplier = result.suppliers[0]
        self.assertEqual(supplier.observation_ids, ("offer-1", "offer-2"))
        self.assertEqual(supplier.offer_count, 2)
        self.assertEqual(supplier.distinct_source_count, 1)
        self.assertEqual(supplier.moq_observation_count, 1)
        self.assertEqual(supplier.incoterm_observation_count, 1)
        self.assertEqual(supplier.rankable_offer_count, 1)
        self.assertEqual(
            supplier.unknown_factors,
            ("certifications", "incoterm", "payment_terms", "supplier_reliability"),
        )
        self.assertEqual(supplier.due_diligence_status, "UNVERIFIED")

    def test_suppliers_stay_separate_and_anonymous_offers_are_not_merged(self) -> None:
        result = summarize_supplier_coverage(
            (
                point("anonymous-2", None),
                point("supplier-b", "Supplier B"),
                point("anonymous-1", None),
                point("supplier-a", "Supplier A"),
            )
        )

        self.assertEqual(
            [supplier.supplier_name for supplier in result.suppliers],
            ["Supplier A", "Supplier B"],
        )
        self.assertEqual(
            result.unidentified_observation_ids,
            ("anonymous-1", "anonymous-2"),
        )

    def test_empty_and_only_anonymous_statuses_are_explicit(self) -> None:
        empty = summarize_supplier_coverage(())
        anonymous = summarize_supplier_coverage((point("anonymous", None),))

        self.assertEqual(empty.status, "NO_SUPPLIER_OBSERVATIONS")
        self.assertEqual(anonymous.status, "NO_IDENTIFIED_SUPPLIERS")
        self.assertEqual(anonymous.unidentified_observation_ids, ("anonymous",))


if __name__ == "__main__":
    unittest.main()
