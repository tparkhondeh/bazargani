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
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResearchReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class SupplierIdentityReviewDecision(StrEnum):
    EVIDENCE_SUPPORTED = "EVIDENCE_SUPPORTED"
    EVIDENCE_CONTRADICTED = "EVIDENCE_CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class SupplierIdentityReviewStatus(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    EVIDENCE_SUPPORTED = "EVIDENCE_SUPPORTED"
    EVIDENCE_CONTRADICTED = "EVIDENCE_CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"


OPPORTUNITY_TRANSITIONS: dict[OpportunityStatus, frozenset[OpportunityStatus]] = {
    OpportunityStatus.RESEARCHING: frozenset(
        {OpportunityStatus.SOURCING, OpportunityStatus.ON_HOLD, OpportunityStatus.LOST}
    ),
    OpportunityStatus.SOURCING: frozenset(
        {
            OpportunityStatus.NEGOTIATING,
            OpportunityStatus.EVALUATING,
            OpportunityStatus.ON_HOLD,
            OpportunityStatus.LOST,
        }
    ),
    OpportunityStatus.NEGOTIATING: frozenset(
        {
            OpportunityStatus.EVALUATING,
            OpportunityStatus.WON,
            OpportunityStatus.LOST,
            OpportunityStatus.ON_HOLD,
        }
    ),
    OpportunityStatus.EVALUATING: frozenset(
        {
            OpportunityStatus.NEGOTIATING,
            OpportunityStatus.WON,
            OpportunityStatus.LOST,
            OpportunityStatus.ON_HOLD,
        }
    ),
    OpportunityStatus.ON_HOLD: frozenset(
        {
            OpportunityStatus.RESEARCHING,
            OpportunityStatus.SOURCING,
            OpportunityStatus.NEGOTIATING,
            OpportunityStatus.EVALUATING,
            OpportunityStatus.LOST,
        }
    ),
    OpportunityStatus.WON: frozenset(),
    OpportunityStatus.LOST: frozenset(),
}


RESEARCH_TRANSITIONS: dict[ResearchRunStatus, frozenset[ResearchRunStatus]] = {
    ResearchRunStatus.CREATED: frozenset({ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}),
    ResearchRunStatus.RUNNING: frozenset(
        {
            ResearchRunStatus.NEEDS_HUMAN_REVIEW,
            ResearchRunStatus.NEEDS_VERIFICATION,
            ResearchRunStatus.PARTIAL,
            ResearchRunStatus.COMPLETED,
            ResearchRunStatus.FAILED,
            ResearchRunStatus.CANCELLED,
        }
    ),
    ResearchRunStatus.NEEDS_VERIFICATION: frozenset(
        {
            ResearchRunStatus.RUNNING,
            ResearchRunStatus.NEEDS_HUMAN_REVIEW,
            ResearchRunStatus.PARTIAL,
            ResearchRunStatus.COMPLETED,
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

MANUAL_RESEARCH_TRANSITIONS: dict[ResearchRunStatus, frozenset[ResearchRunStatus]] = {
    ResearchRunStatus.CREATED: frozenset(
        {ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}
    ),
    ResearchRunStatus.RUNNING: frozenset(
        {ResearchRunStatus.FAILED, ResearchRunStatus.CANCELLED}
    ),
    ResearchRunStatus.FAILED: frozenset(
        {ResearchRunStatus.RUNNING, ResearchRunStatus.CANCELLED}
    ),
    ResearchRunStatus.NEEDS_VERIFICATION: frozenset(),
    ResearchRunStatus.NEEDS_HUMAN_REVIEW: frozenset(),
    ResearchRunStatus.PARTIAL: frozenset(),
    ResearchRunStatus.COMPLETED: frozenset(),
    ResearchRunStatus.CANCELLED: frozenset(),
}

REVIEWABLE_RESEARCH_STATUSES = frozenset(
    {
        ResearchRunStatus.NEEDS_VERIFICATION,
        ResearchRunStatus.NEEDS_HUMAN_REVIEW,
        ResearchRunStatus.PARTIAL,
    }
)


class InvalidTransitionError(ValueError):
    pass


class VersionConflictError(RuntimeError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


def ensure_opportunity_transition(
    current: OpportunityStatus,
    target: OpportunityStatus,
) -> None:
    if target not in OPPORTUNITY_TRANSITIONS[current]:
        raise InvalidTransitionError(f"invalid opportunity transition: {current} -> {target}")


def ensure_research_transition(current: ResearchRunStatus, target: ResearchRunStatus) -> None:
    if target not in RESEARCH_TRANSITIONS[current]:
        raise InvalidTransitionError(f"invalid research transition: {current} -> {target}")


def ensure_manual_research_transition(
    current: ResearchRunStatus,
    target: ResearchRunStatus,
) -> None:
    if target not in MANUAL_RESEARCH_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"manual transition is not permitted: {current} -> {target}"
        )


def review_target_status(
    current: ResearchRunStatus,
    decision: ResearchReviewDecision,
) -> ResearchRunStatus:
    if current not in REVIEWABLE_RESEARCH_STATUSES:
        raise InvalidTransitionError(f"research run is not reviewable in status {current}")
    target = {
        ResearchReviewDecision.APPROVE: ResearchRunStatus.COMPLETED,
        ResearchReviewDecision.REJECT: ResearchRunStatus.CANCELLED,
    }[decision]
    ensure_research_transition(current, target)
    return target
