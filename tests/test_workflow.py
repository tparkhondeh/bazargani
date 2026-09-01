import unittest

from trade_agent.domain.workflow import (
    InvalidTransitionError,
    OpportunityStatus,
    ResearchReviewDecision,
    ResearchRunStatus,
    ensure_manual_research_transition,
    ensure_opportunity_transition,
    ensure_research_transition,
    review_target_status,
)


class WorkflowTests(unittest.TestCase):
    def test_opportunity_progress_and_resume_transitions_are_explicit(self) -> None:
        ensure_opportunity_transition(
            OpportunityStatus.RESEARCHING,
            OpportunityStatus.SOURCING,
        )
        ensure_opportunity_transition(
            OpportunityStatus.EVALUATING,
            OpportunityStatus.NEGOTIATING,
        )
        ensure_opportunity_transition(
            OpportunityStatus.ON_HOLD,
            OpportunityStatus.EVALUATING,
        )

    def test_opportunity_cannot_skip_policy_or_reopen_terminal_status(self) -> None:
        for current, target in (
            (OpportunityStatus.RESEARCHING, OpportunityStatus.WON),
            (OpportunityStatus.SOURCING, OpportunityStatus.SOURCING),
            (OpportunityStatus.WON, OpportunityStatus.NEGOTIATING),
            (OpportunityStatus.LOST, OpportunityStatus.RESEARCHING),
        ):
            with self.subTest(current=current, target=target), self.assertRaisesRegex(
                InvalidTransitionError,
                "invalid opportunity transition",
            ):
                ensure_opportunity_transition(current, target)

    def test_valid_transition(self) -> None:
        ensure_research_transition(ResearchRunStatus.CREATED, ResearchRunStatus.RUNNING)

    def test_terminal_transition_is_rejected(self) -> None:
        with self.assertRaisesRegex(InvalidTransitionError, "invalid research transition"):
            ensure_research_transition(ResearchRunStatus.COMPLETED, ResearchRunStatus.RUNNING)

    def test_verification_result_can_be_escalated(self) -> None:
        ensure_research_transition(
            ResearchRunStatus.NEEDS_VERIFICATION,
            ResearchRunStatus.NEEDS_HUMAN_REVIEW,
        )

    def test_manual_transition_cannot_claim_a_system_or_review_outcome(self) -> None:
        with self.assertRaisesRegex(InvalidTransitionError, "manual transition"):
            ensure_manual_research_transition(
                ResearchRunStatus.RUNNING,
                ResearchRunStatus.COMPLETED,
            )
        with self.assertRaisesRegex(InvalidTransitionError, "manual transition"):
            ensure_manual_research_transition(
                ResearchRunStatus.NEEDS_VERIFICATION,
                ResearchRunStatus.RUNNING,
            )

    def test_review_decisions_have_explicit_terminal_targets(self) -> None:
        self.assertEqual(
            review_target_status(
                ResearchRunStatus.NEEDS_VERIFICATION,
                ResearchReviewDecision.APPROVE,
            ),
            ResearchRunStatus.COMPLETED,
        )
        self.assertEqual(
            review_target_status(
                ResearchRunStatus.NEEDS_HUMAN_REVIEW,
                ResearchReviewDecision.REJECT,
            ),
            ResearchRunStatus.CANCELLED,
        )

    def test_non_reviewable_run_rejects_a_review_decision(self) -> None:
        with self.assertRaisesRegex(InvalidTransitionError, "not reviewable"):
            review_target_status(
                ResearchRunStatus.RUNNING,
                ResearchReviewDecision.APPROVE,
            )


if __name__ == "__main__":
    unittest.main()
