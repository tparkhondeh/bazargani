import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_agent.application.evidence_freshness import (
    EvidenceFreshnessPoint,
    analyze_evidence_freshness,
)
from trade_agent.domain.errors import PublicInputError

EVALUATED_AT = datetime(2026, 9, 1, 12, tzinfo=UTC)


def point(
    evidence_id: str,
    retrieved_at: datetime,
    usage_count: int = 1,
) -> EvidenceFreshnessPoint:
    return EvidenceFreshnessPoint(
        evidence_id=evidence_id,
        fingerprint_sha256="a" * 64,
        classification="FACT",
        confidence="HIGH",
        source_name=f"Source {evidence_id}",
        source_url=f"https://example.com/{evidence_id}",
        retrieved_at=retrieved_at,
        usage_count=usage_count,
    )


class EvidenceFreshnessTests(unittest.TestCase):
    def test_current_stale_and_future_boundaries_are_exact(self) -> None:
        result = analyze_evidence_freshness(
            (
                point("stale", EVALUATED_AT - timedelta(days=30, seconds=1)),
                point("current", EVALUATED_AT - timedelta(days=30), 3),
                point("skew", EVALUATED_AT + timedelta(minutes=5)),
                point("future", EVALUATED_AT + timedelta(minutes=5, microseconds=1)),
            ),
            evaluated_at=EVALUATED_AT,
            validation_policy_version="fixture-policy",
        )

        self.assertEqual(result.status, "FUTURE_DATED_EVIDENCE_RECORDED")
        self.assertEqual(result.evidence_count, 4)
        self.assertEqual(result.current_count, 1)
        self.assertEqual(result.within_clock_skew_count, 1)
        self.assertEqual(result.stale_count, 1)
        self.assertEqual(result.future_dated_count, 1)
        by_id = {item.evidence_id: item for item in result.items}
        self.assertEqual(by_id["current"].age_seconds, Decimal("2592000"))
        self.assertEqual(by_id["skew"].age_seconds, Decimal("-300"))
        self.assertEqual(by_id["future"].freshness_status, "FUTURE_DATED")
        self.assertEqual(by_id["current"].usage_count, 3)

    def test_empty_summary_is_explicit(self) -> None:
        result = analyze_evidence_freshness(
            (),
            evaluated_at=EVALUATED_AT,
            validation_policy_version="fixture-policy",
        )
        self.assertEqual(result.status, "NO_EVIDENCE")
        self.assertEqual(result.evidence_count, 0)

    def test_invalid_identity_time_policy_and_usage_fail_closed(self) -> None:
        duplicate = point("same", EVALUATED_AT)
        with self.assertRaisesRegex(PublicInputError, "IDs must be unique"):
            analyze_evidence_freshness(
                (duplicate, duplicate),
                evaluated_at=EVALUATED_AT,
                validation_policy_version="fixture-policy",
            )
        with self.assertRaisesRegex(PublicInputError, "timezone-aware"):
            analyze_evidence_freshness(
                (point("naive", datetime(2026, 9, 1)),),
                evaluated_at=EVALUATED_AT,
                validation_policy_version="fixture-policy",
            )
        with self.assertRaisesRegex(PublicInputError, "cannot be negative"):
            analyze_evidence_freshness(
                (point("negative", EVALUATED_AT, -1),),
                evaluated_at=EVALUATED_AT,
                validation_policy_version="fixture-policy",
            )
        with self.assertRaisesRegex(PublicInputError, "version is required"):
            analyze_evidence_freshness(
                (),
                evaluated_at=EVALUATED_AT,
                validation_policy_version=" ",
            )


if __name__ == "__main__":
    unittest.main()
