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


def summarize_data_gaps(
    issues: tuple[DataGapIssue, ...],
    declared_unknowns: tuple[str, ...],
) -> DataGapSummary:
    invalid_severities = sorted(
        {issue.severity for issue in issues if issue.severity not in _SEVERITY_ORDER}
    )
    if invalid_severities:
        raise PublicInputError("data-gap issue severity must be ERROR or WARNING")

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
    error_count = sum(issue.severity == "ERROR" for issue in ordered_issues)
    warning_count = sum(issue.severity == "WARNING" for issue in ordered_issues)

    if error_count:
        status = "GAPS_REQUIRE_HUMAN_REVIEW"
    elif warning_count or ordered_unknowns:
        status = "GAPS_REQUIRE_VERIFICATION"
    else:
        status = "NO_RECORDED_GAPS"

    return DataGapSummary(
        status=status,
        issue_count=len(ordered_issues),
        error_count=error_count,
        warning_count=warning_count,
        declared_unknown_count=len(ordered_unknowns),
        issues=ordered_issues,
        declared_unknowns=ordered_unknowns,
        limitations=(
            "data gaps reflect only persisted validation issues and declared unknowns",
            "absence of a recorded gap does not prove commercial completeness",
            "closing a gap requires verified evidence in a new immutable research run",
        ),
    )
