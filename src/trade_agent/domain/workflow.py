from __future__ import annotations

from enum import StrEnum


class OpportunityStatus(StrEnum):
    RESEARCHING = "RESEARCHING"
    SOURCING = "SOURCING"
    NEGOTIATING = "NEGOTIATING"
    EVALUATING = "EVALUATING"
    WON = "WON"
    LOST = "LOST"
    ON_HOLD = "ON_HOLD"


class ResearchRunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


RESEARCH_TRANSITIONS: dict[ResearchRunStatus, frozenset[ResearchRunStatus]] = {
    ResearchRunStatus.CREATED: frozenset({ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}),
    ResearchRunStatus.RUNNING: frozenset(
        {
            ResearchRunStatus.NEEDS_HUMAN_REVIEW,
            ResearchRunStatus.PARTIAL,
            ResearchRunStatus.COMPLETED,
            ResearchRunStatus.FAILED,
            ResearchRunStatus.CANCELLED,
        }
    ),
    ResearchRunStatus.NEEDS_HUMAN_REVIEW: frozenset(
        {
            ResearchRunStatus.RUNNING,
            ResearchRunStatus.PARTIAL,
            ResearchRunStatus.COMPLETED,
            ResearchRunStatus.CANCELLED,
        }
    ),
    ResearchRunStatus.PARTIAL: frozenset(
        {ResearchRunStatus.RUNNING, ResearchRunStatus.COMPLETED, ResearchRunStatus.CANCELLED}
    ),
    ResearchRunStatus.COMPLETED: frozenset(),
    ResearchRunStatus.FAILED: frozenset({ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}),
    ResearchRunStatus.CANCELLED: frozenset(),
}


class InvalidTransitionError(ValueError):
    pass


class VersionConflictError(RuntimeError):
    pass


def ensure_research_transition(current: ResearchRunStatus, target: ResearchRunStatus) -> None:
    if target not in RESEARCH_TRANSITIONS[current]:
        raise InvalidTransitionError(f"invalid research transition: {current} -> {target}")
