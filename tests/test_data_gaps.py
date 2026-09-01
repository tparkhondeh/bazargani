import unittest

from trade_agent.application.data_gaps import (
    DataGapIssue,
    summarize_data_gap_counts,
    summarize_data_gaps,
)
from trade_agent.domain.errors import PublicInputError


def issue(code: str, severity: str) -> DataGapIssue:
    return DataGapIssue(
        code=code,
        severity=severity,
        message_fa=f"message for {code}",
        subject_type="RESEARCH_CASE",
        subject_id="case-1",
        details=None,
    )


class DataGapSummaryTests(unittest.TestCase):
    def test_empty_summary_does_not_claim_completeness(self) -> None:
        summary = summarize_data_gaps((), ())

        self.assertEqual(summary.status, "NO_RECORDED_GAPS")
        self.assertEqual(summary.issue_count, 0)
        self.assertEqual(summary.declared_unknown_count, 0)
        self.assertIn("does not prove commercial completeness", summary.limitations[1])

    def test_warning_and_unknowns_are_counted_and_sorted(self) -> None:
        summary = summarize_data_gaps(
            (issue("Z_WARNING", "WARNING"), issue("A_WARNING", "WARNING")),
            ("unknown z", "unknown a"),
        )

        self.assertEqual(summary.status, "GAPS_REQUIRE_VERIFICATION")
        self.assertEqual(summary.warning_count, 2)
        self.assertEqual(summary.error_count, 0)
        self.assertEqual(summary.declared_unknown_count, 2)
        self.assertEqual([item.code for item in summary.issues], ["A_WARNING", "Z_WARNING"])
        self.assertEqual(summary.declared_unknowns, ("unknown a", "unknown z"))

    def test_error_takes_precedence_and_unknown_severity_fails_closed(self) -> None:
        summary = summarize_data_gaps(
            (issue("WARNING", "WARNING"), issue("ERROR", "ERROR")),
            (),
        )
        self.assertEqual(summary.status, "GAPS_REQUIRE_HUMAN_REVIEW")
        self.assertEqual(summary.error_count, 1)
        self.assertEqual(summary.warning_count, 1)

        with self.assertRaisesRegex(PublicInputError, "ERROR or WARNING"):
            summarize_data_gaps((issue("UNKNOWN", "INFO"),), ())

    def test_count_only_summary_reuses_the_same_status_policy(self) -> None:
        verification = summarize_data_gap_counts((), 2)
        human_review = summarize_data_gap_counts(("WARNING", "ERROR"), 0)

        self.assertEqual(verification.status, "GAPS_REQUIRE_VERIFICATION")
        self.assertEqual(verification.issue_count, 0)
        self.assertEqual(verification.declared_unknown_count, 2)
        self.assertEqual(human_review.status, "GAPS_REQUIRE_HUMAN_REVIEW")
        self.assertEqual(human_review.error_count, 1)
        with self.assertRaisesRegex(PublicInputError, "cannot be negative"):
            summarize_data_gap_counts((), -1)
        with self.assertRaisesRegex(PublicInputError, "ERROR or WARNING"):
            summarize_data_gap_counts(("INFO",), 0)


if __name__ == "__main__":
    unittest.main()
