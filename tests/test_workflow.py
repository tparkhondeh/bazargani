import unittest

from trade_agent.domain.workflow import (
    InvalidTransitionError,
    ResearchRunStatus,
    ensure_research_transition,
)


class WorkflowTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
