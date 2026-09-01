from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_agent.domain.errors import PublicInputError
from trade_agent.domain.models import Evidence

DEFAULT_MAX_EVIDENCE_AGE = timedelta(days=30)
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessPoint:
    evidence_id: str
    fingerprint_sha256: str
    classification: str
    confidence: str
    source_name: str
    source_url: str
    retrieved_at: datetime
    usage_count: int


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessItem:
    evidence_id: str
    fingerprint_sha256: str
    classification: str
    confidence: str
    source_name: str
    source_url: str
    retrieved_at: datetime
    age_seconds: Decimal
    usage_count: int
    freshness_status: str


@dataclass(frozen=True, slots=True)
class EvidenceFreshnessSummary:
    status: str
    validation_policy_version: str
    evaluated_at: datetime
    max_age_seconds: int
    future_clock_skew_seconds: int
    evidence_count: int
    current_count: int
    within_clock_skew_count: int
    stale_count: int
    future_dated_count: int
    items: tuple[EvidenceFreshnessItem, ...]
    limitations: tuple[str, ...]


def evidence_fingerprint_sha256(evidence: Evidence) -> str:
    canonical = json.dumps(
        {
            "classification": evidence.classification.value,
            "source_name": evidence.source_name,
            "source_url": evidence.source_url,
            "retrieved_at": evidence.retrieved_at.isoformat(),
            "raw_value": evidence.raw_value,
            "confidence": evidence.confidence.value,
            "transformation": evidence.transformation,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise PublicInputError(f"{label} must be timezone-aware")
    return value.astimezone(UTC)


def _seconds(value: timedelta) -> Decimal:
    whole_seconds = value.days * 86_400 + value.seconds
    return Decimal(whole_seconds) + Decimal(value.microseconds) / Decimal(1_000_000)


def analyze_evidence_freshness(
    points: tuple[EvidenceFreshnessPoint, ...],
    *,
    evaluated_at: datetime,
    validation_policy_version: str,
) -> EvidenceFreshnessSummary:
    if not validation_policy_version.strip():
        raise PublicInputError("validation policy version is required")
    evaluation_time = _utc(evaluated_at, "evaluated_at")
    evidence_ids = [point.evidence_id for point in points]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise PublicInputError("evidence-freshness IDs must be unique")
    if any(point.usage_count < 0 for point in points):
        raise PublicInputError("evidence usage count cannot be negative")

    current_count = 0
    within_clock_skew_count = 0
    stale_count = 0
    future_dated_count = 0
    items: list[EvidenceFreshnessItem] = []
    for point in points:
        retrieved_at = _utc(point.retrieved_at, "retrieved_at")
        age = evaluation_time - retrieved_at
        if age < -MAX_FUTURE_CLOCK_SKEW:
            freshness_status = "FUTURE_DATED"
            future_dated_count += 1
        elif age < timedelta(0):
            freshness_status = "WITHIN_ALLOWED_FUTURE_CLOCK_SKEW"
            within_clock_skew_count += 1
        elif age > DEFAULT_MAX_EVIDENCE_AGE:
            freshness_status = "STALE"
            stale_count += 1
        else:
            freshness_status = "CURRENT"
            current_count += 1
        items.append(
            EvidenceFreshnessItem(
                evidence_id=point.evidence_id,
                fingerprint_sha256=point.fingerprint_sha256,
                classification=point.classification,
                confidence=point.confidence,
                source_name=point.source_name,
                source_url=point.source_url,
                retrieved_at=retrieved_at,
                age_seconds=_seconds(age),
                usage_count=point.usage_count,
                freshness_status=freshness_status,
            )
        )

    if not points:
        status = "NO_EVIDENCE"
    elif future_dated_count:
        status = "FUTURE_DATED_EVIDENCE_RECORDED"
    elif stale_count:
        status = "STALE_EVIDENCE_RECORDED"
    else:
        status = "EVIDENCE_WITHIN_FRESHNESS_POLICY"
    items.sort(key=lambda item: (item.retrieved_at, item.evidence_id))
    return EvidenceFreshnessSummary(
        status=status,
        validation_policy_version=validation_policy_version,
        evaluated_at=evaluation_time,
        max_age_seconds=int(DEFAULT_MAX_EVIDENCE_AGE.total_seconds()),
        future_clock_skew_seconds=int(MAX_FUTURE_CLOCK_SKEW.total_seconds()),
        evidence_count=len(items),
        current_count=current_count,
        within_clock_skew_count=within_clock_skew_count,
        stale_count=stale_count,
        future_dated_count=future_dated_count,
        items=tuple(items),
        limitations=(
            "freshness is measured against the immutable run evaluation time, not now",
            "freshness does not prove source authority, accuracy, independence, or fitness",
            "policy thresholds are review controls, not legal or commercial expiry rules",
            "raw evidence content is intentionally excluded from this projection",
        ),
    )

