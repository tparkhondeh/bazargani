from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trade_agent.domain.errors import PublicInputError

_SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1}


@dataclass(frozen=True, slots=True)
class DataGapIssue:
    code: str
    severity: str
    message_fa: str
    subject_type: str
    subject_id: str | None
    details: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class DataGapSummary:
    status: str
    issue_count: int
    error_count: int
    warning_count: int
    declared_unknown_count: int
    issues: tuple[DataGapIssue, ...]
    declared_unknowns: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataGapCounts:
    status: str
    issue_count: int
    error_count: int
    warning_count: int
    declared_unknown_count: int


def summarize_data_gap_counts(
    issue_severities: tuple[str, ...],
    declared_unknown_count: int,
) -> DataGapCounts:
    invalid_severities = sorted(
        {severity for severity in issue_severities if severity not in _SEVERITY_ORDER}
    )
    if invalid_severities:
        raise PublicInputError("data-gap issue severity must be ERROR or WARNING")
    if declared_unknown_count < 0:
        raise PublicInputError("declared unknown count cannot be negative")

    error_count = sum(severity == "ERROR" for severity in issue_severities)
    warning_count = sum(severity == "WARNING" for severity in issue_severities)
    if error_count:
        status = "GAPS_REQUIRE_HUMAN_REVIEW"
    elif warning_count or declared_unknown_count:
        status = "GAPS_REQUIRE_VERIFICATION"
    else:
        status = "NO_RECORDED_GAPS"
    return DataGapCounts(
        status=status,
        issue_count=len(issue_severities),
        error_count=error_count,
        warning_count=warning_count,
        declared_unknown_count=declared_unknown_count,
    )


def summarize_data_gaps(
    issues: tuple[DataGapIssue, ...],
    declared_unknowns: tuple[str, ...],
) -> DataGapSummary:
    counts = summarize_data_gap_counts(
        tuple(issue.severity for issue in issues),
        len(declared_unknowns),
    )
    ordered_issues = tuple(
        sorted(
            issues,
            key=lambda issue: (
                _SEVERITY_ORDER[issue.severity],
                issue.code,
                issue.subject_type,
                issue.subject_id or "",
                issue.message_fa,
            ),
        )
    )
    ordered_unknowns = tuple(sorted(declared_unknowns))

    return DataGapSummary(
        status=counts.status,
        issue_count=counts.issue_count,
        error_count=counts.error_count,
        warning_count=counts.warning_count,
        declared_unknown_count=counts.declared_unknown_count,
        issues=ordered_issues,
        declared_unknowns=ordered_unknowns,
        limitations=(
            "data gaps reflect only persisted validation issues and declared unknowns",
            "absence of a recorded gap does not prove commercial completeness",
            "closing a gap requires verified evidence in a new immutable research run",
        ),
    )
