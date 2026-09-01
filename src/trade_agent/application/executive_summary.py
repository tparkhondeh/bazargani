from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trade_agent.domain.errors import PublicInputError


@dataclass(frozen=True, slots=True)
class ExecutiveSupplierCandidate:
    observation_id: str
    supplier_name: str
    original_amount: Decimal
    original_currency: str
    normalized_amount: Decimal
    normalized_currency: str
    total_score: int
    source_url: str
    evidence_classification: str
    evidence_confidence: str
    due_diligence_status: str = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class ExecutiveDecisionSummary:
    decision_status: str
    recommendation_code: str
    supplier_candidate_status: str
    leading_supplier_candidates: tuple[ExecutiveSupplierCandidate, ...]
    base_landed_cost_per_unit: Decimal
    base_landed_cost_currency: str
    iran_market_benchmark_status: str
    iran_market_unit_price: Decimal | None
    potential_gross_spread_per_unit: Decimal | None
    potential_gross_spread_percent: Decimal | None
    data_gap_status: str
    data_gap_issue_count: int
    declared_unknown_count: int
    confidence_score: int
    confidence_label: str
    limitations: tuple[str, ...]


def build_executive_summary(
    *,
    validation_disposition: str,
    confidence_score: int,
    confidence_label: str,
    base_landed_cost_per_unit: Decimal,
    base_landed_cost_currency: str,
    leading_supplier_candidates: tuple[ExecutiveSupplierCandidate, ...],
    data_gap_status: str,
    data_gap_issue_count: int,
    declared_unknown_count: int,
) -> ExecutiveDecisionSummary:
    if not 0 <= confidence_score <= 100:
        raise PublicInputError("confidence score must be between 0 and 100")
    if base_landed_cost_per_unit < 0:
        raise PublicInputError("base landed cost per unit cannot be negative")
    if data_gap_issue_count < 0 or declared_unknown_count < 0:
        raise PublicInputError("data-gap counts cannot be negative")

    if validation_disposition == "NEEDS_HUMAN_REVIEW":
        decision_status = "HUMAN_REVIEW_REQUIRED"
        recommendation = "RESOLVE_ERRORS_BEFORE_PURCHASE"
    elif validation_disposition == "NEEDS_VERIFICATION":
        decision_status = "VERIFICATION_REQUIRED"
        recommendation = "VERIFY_GAPS_BEFORE_PURCHASE"
    elif validation_disposition == "PASSED":
        decision_status = "COMMERCIAL_REVIEW_REQUIRED"
        recommendation = "REVIEW_TERMS_BEFORE_PURCHASE"
    else:
        raise PublicInputError("unsupported validation disposition")

    ordered_candidates = tuple(
        sorted(
            leading_supplier_candidates,
            key=lambda item: (
                item.normalized_currency,
                item.normalized_amount,
                item.supplier_name,
                item.observation_id,
            ),
        )
    )
    if not ordered_candidates:
        candidate_status = "NO_RANKED_SUPPLIER_CANDIDATE"
    elif len(ordered_candidates) == 1:
        candidate_status = "SINGLE_UNVERIFIED_CANDIDATE"
    else:
        candidate_status = "MULTIPLE_LEADING_UNVERIFIED_CANDIDATES"

    return ExecutiveDecisionSummary(
        decision_status=decision_status,
        recommendation_code=recommendation,
        supplier_candidate_status=candidate_status,
        leading_supplier_candidates=ordered_candidates,
        base_landed_cost_per_unit=base_landed_cost_per_unit,
        base_landed_cost_currency=base_landed_cost_currency,
        iran_market_benchmark_status="WITHHELD_NO_APPROVED_BENCHMARK",
        iran_market_unit_price=None,
        potential_gross_spread_per_unit=None,
        potential_gross_spread_percent=None,
        data_gap_status=data_gap_status,
        data_gap_issue_count=data_gap_issue_count,
        declared_unknown_count=declared_unknown_count,
        confidence_score=confidence_score,
        confidence_label=confidence_label,
        limitations=(
            "supplier candidates rank submitted offers and remain unverified",
            "landed cost depends on the displayed evidence and assumptions",
            "Iran market price and gross spread require an approved comparable benchmark",
            "this summary never authorizes or automates a purchase",
        ),
    )
