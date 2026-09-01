from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trade_agent.domain.models import Confidence
from trade_agent.domain.workflow import ResearchReviewDecision, ResearchRunStatus


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str


class OpportunityCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=300)
    quantity: int = Field(gt=0)
    target_market: str = Field(min_length=1, max_length=200)


class OpportunityView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_name: str
    quantity: int
    target_market: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ResearchRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    opportunity_id: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ResearchRunTransition(BaseModel):
    target_status: ResearchRunStatus
    expected_version: int = Field(gt=0)


class ResearchReviewSubmit(BaseModel):
    decision: ResearchReviewDecision
    rationale: str = Field(min_length=3, max_length=2_000)
    expected_version: int = Field(gt=0)


class ResearchReviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    research_run_id: str
    reviewer_actor_id: str
    decision: ResearchReviewDecision
    rationale: str
    previous_status: ResearchRunStatus
    resulting_status: ResearchRunStatus
    previous_version: int
    resulting_version: int
    created_at: datetime


class EvidenceBundleSubmit(BaseModel):
    expected_version: int = Field(gt=0)
    bundle: dict[str, Any]


class ResearchCompletionView(BaseModel):
    research_run_id: str
    status: str
    version: int
    evidence_count: int
    price_observation_count: int
    product_match_count: int
    supplier_ranking_count: int
    fx_rate_count: int
    scenario_count: int
    validation_disposition: str
    validation_issue_count: int
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: Confidence
    report_sha256: str
    idempotency_replayed: bool


class ValidationIssueView(BaseModel):
    code: str
    severity: str
    message_fa: str
    subject_type: str
    subject_id: str | None
    details: dict[str, Any] | None


class ResearchValidationView(BaseModel):
    research_run_id: str
    policy_version: str
    disposition: str
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: Confidence
    evaluated_at: datetime
    issues: list[ValidationIssueView]


class ProductMatchView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    external_observation_id: str
    classification: str
    score: int = Field(ge=0, le=100)
    name_similarity: Decimal = Field(ge=0, le=1)
    requested_attributes: dict[str, str]
    observed_attributes: dict[str, str]
    matched_attributes: list[str]
    conflicting_attributes: list[str]
    missing_attributes: list[str]
    explanation_fa: list[str]
    policy_version: str


class SupplierOfferRankingView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    external_observation_id: str
    supplier_name: str | None
    comparison_group: str
    rank: int | None
    eligible_for_quantity: bool
    rankable: bool
    normalized_amount: Decimal | None
    normalized_currency: str | None
    total_score: int = Field(ge=0, le=100)
    component_scores: dict[str, int]
    unknown_factors: list[str]
    explanation_fa: list[str]
    policy_version: str


class DecisionReportView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_run_id: str
    case_id: str
    format: str
    content: str
    content_sha256: str
    generated_at: datetime


class ParseRequestInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ParsedTradeRequestView(BaseModel):
    original_text: str
    normalized_text: str
    product_name: str | None
    quantity: int | None
    quantity_unit: str | None
    origin_market: str | None
    destination: str | None
    field_confidence: dict[str, Confidence]
    assumptions: tuple[str, ...]
    critical_questions: tuple[str, ...]
    can_start_research: bool
