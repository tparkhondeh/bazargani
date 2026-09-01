from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SupplierIdentityClaimPoint:
    claim_id: str
    observation_id: str
    quoted_supplier_name: str | None
    claimed_legal_name: str
    jurisdiction: str
    registration_number: str
    source_name: str
    source_url: str
    retrieved_at: datetime
    evidence_classification: str
    evidence_confidence: str
    transformation: str | None


@dataclass(frozen=True, slots=True)
class SupplierIdentityClaimItem:
    claim_id: str
    observation_id: str
    quoted_supplier_name: str | None
    claimed_legal_name: str
    jurisdiction: str
    registration_number: str
    review_status: str
    source_name: str
    source_url: str
    retrieved_at: datetime
    evidence_classification: str
    evidence_confidence: str
    transformation: str | None


@dataclass(frozen=True, slots=True)
class SupplierIdentityClaimSummary:
    status: str
    claim_count: int
    claims: tuple[SupplierIdentityClaimItem, ...]
    limitations: tuple[str, ...]


def summarize_supplier_identity_claims(
    points: tuple[SupplierIdentityClaimPoint, ...],
) -> SupplierIdentityClaimSummary:
    claims = tuple(
        SupplierIdentityClaimItem(
            claim_id=point.claim_id,
            observation_id=point.observation_id,
            quoted_supplier_name=point.quoted_supplier_name,
            claimed_legal_name=point.claimed_legal_name,
            jurisdiction=point.jurisdiction,
            registration_number=point.registration_number,
            review_status="UNREVIEWED",
            source_name=point.source_name,
            source_url=point.source_url,
            retrieved_at=point.retrieved_at,
            evidence_classification=point.evidence_classification,
            evidence_confidence=point.evidence_confidence,
            transformation=point.transformation,
        )
        for point in sorted(points, key=lambda item: (item.observation_id, item.claim_id))
    )
    return SupplierIdentityClaimSummary(
        status=(
            "UNREVIEWED_IDENTITY_CLAIMS"
            if claims
            else "NO_SUPPLIER_IDENTITY_CLAIMS"
        ),
        claim_count=len(claims),
        claims=claims,
        limitations=(
            "a claim preserves a source assertion and does not verify legal identity",
            "claims are offer-scoped and names are not merged into a supplier profile",
            "review status remains UNREVIEWED until an append-only review is recorded",
            "claims do not change offer ranking or supplier due-diligence status",
        ),
    )
