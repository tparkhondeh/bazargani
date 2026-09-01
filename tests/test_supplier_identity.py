import unittest
from dataclasses import replace
from datetime import UTC, datetime

from trade_agent.application.supplier_identity import (
    SupplierIdentityClaimPoint,
    summarize_supplier_identity_claims,
)
from trade_agent.domain.workflow import SupplierIdentityReviewStatus


def point(
    claim_id: str,
    observation_id: str,
) -> SupplierIdentityClaimPoint:
    return SupplierIdentityClaimPoint(
        claim_id=claim_id,
        observation_id=observation_id,
        quoted_supplier_name="Quoted Supplier Fixture",
        claimed_legal_name="Claimed Legal Supplier Fixture",
        jurisdiction="Fixture Jurisdiction",
        registration_number="FIXTURE-001",
        source_name="Synthetic registry fixture",
        source_url="https://example.com/synthetic-registry",
        retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
        evidence_classification="FACT",
        evidence_confidence="HIGH",
        transformation="synthetic contract fixture",
    )


class SupplierIdentityClaimTests(unittest.TestCase):
    def test_claims_are_deterministic_offer_scoped_and_unreviewed(self) -> None:
        summary = summarize_supplier_identity_claims(
            (
                point("claim-b", "offer-b"),
                point("claim-a", "offer-a"),
            )
        )

        self.assertEqual(summary.status, "UNREVIEWED_IDENTITY_CLAIMS")
        self.assertEqual(summary.claim_count, 2)
        self.assertEqual(
            [claim.claim_id for claim in summary.claims],
            ["claim-a", "claim-b"],
        )
        self.assertTrue(all(claim.review_status == "UNREVIEWED" for claim in summary.claims))
        self.assertIn("offer-scoped", " ".join(summary.limitations))
        self.assertIn("do not change offer ranking", " ".join(summary.limitations))

    def test_empty_summary_does_not_invent_identity_evidence(self) -> None:
        summary = summarize_supplier_identity_claims(())

        self.assertEqual(summary.status, "NO_SUPPLIER_IDENTITY_CLAIMS")
        self.assertEqual(summary.claim_count, 0)
        self.assertEqual(summary.claims, ())

    def test_latest_review_state_is_projected_without_claiming_verified_identity(
        self,
    ) -> None:
        reviewed_at = datetime(2026, 9, 1, 12, tzinfo=UTC)
        supported = replace(
            point("claim-a", "offer-a"),
            review_status=SupplierIdentityReviewStatus.EVIDENCE_SUPPORTED,
            review_version=1,
            latest_reviewed_at=reviewed_at,
        )
        mixed = summarize_supplier_identity_claims(
            (supported, point("claim-b", "offer-b"))
        )

        self.assertEqual(mixed.status, "UNREVIEWED_IDENTITY_CLAIMS")
        self.assertEqual(mixed.claims[0].review_version, 1)
        self.assertEqual(mixed.claims[0].latest_reviewed_at, reviewed_at)

        fully_reviewed = summarize_supplier_identity_claims(
            (
                supported,
                replace(
                    point("claim-b", "offer-b"),
                    review_status=SupplierIdentityReviewStatus.INCONCLUSIVE,
                    review_version=2,
                    latest_reviewed_at=reviewed_at,
                ),
            )
        )

        self.assertEqual(fully_reviewed.status, "REVIEWED_IDENTITY_CLAIMS")
        self.assertIn(
            "not verified supplier identity",
            " ".join(fully_reviewed.limitations),
        )


if __name__ == "__main__":
    unittest.main()
