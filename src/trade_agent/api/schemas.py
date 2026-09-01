from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from trade_agent.domain.models import Confidence
from trade_agent.domain.workflow import (
    OpportunityStatus,
    ResearchReviewDecision,
    ResearchRunStatus,
)


class ValidationErrorDetail(BaseModel):
    location: list[str]
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str
    details: list[ValidationErrorDetail] | None = None


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
    next_action: str | None
    deadline: AwareDatetime | None
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    @field_validator("deadline", mode="before")
    @classmethod
    def normalize_naive_database_deadline(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class OpportunityPageView(BaseModel):
    items: list[OpportunityView]
    next_cursor: str | None


class OpportunityTransition(BaseModel):
    target_status: OpportunityStatus
    expected_version: int = Field(gt=0)


class OpportunityContextUpdate(BaseModel):
    expected_version: int = Field(gt=0)
    next_action: str | None = Field(default=None, min_length=1, max_length=500)
    deadline: AwareDatetime | None = None
    notes: str | None = Field(default=None, min_length=1, max_length=10_000)


class ResearchRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    opportunity_id: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ResearchRunPageView(BaseModel):
    items: list[ResearchRunView]
    next_cursor: str | None


class AuditEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: str
    correlation_id: str
    aggregate_type: str
    aggregate_id: str
    action: str
    payload: dict[str, Any]
    occurred_at: datetime


class AuditEventPageView(BaseModel):
    items: list[AuditEventView]
    next_cursor: str | None


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


class EvidenceView(BaseModel):
    classification: str
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    raw_value: str
    confidence: Confidence
    transformation: str | None

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def normalize_naive_database_retrieval_time(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class EvidenceUsageView(BaseModel):
    kind: str
    subject_id: str


class EvidenceSummaryView(BaseModel):
    id: str
    classification: str
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    confidence: Confidence
    transformation: str | None
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usages: list[EvidenceUsageView]

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def normalize_naive_database_retrieval_time(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ReferenceRateView(BaseModel):
    base_currency: str
    quote_currency: str
    rate: Decimal
    rate_type: str
    effective_at: datetime | None
    evidence: EvidenceView


class ScenarioFXRateView(BaseModel):
    scenario_name: str
    base_currency: str
    quote_currency: str
    rate: Decimal
    rate_type: str
    effective_at: AwareDatetime | None
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    evidence_classification: str
    evidence_confidence: Confidence
    transformation: str | None

    @field_validator("effective_at", "retrieved_at", mode="before")
    @classmethod
    def normalize_naive_database_time(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ProviderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    enabled: bool
    retrieval_method: str
    evidence_classification: str
    terms_review_status: str
    supported_scope: tuple[str, ...]
    fixed_hosts: tuple[str, ...]
    cache_ttl_seconds: int
    declared_rate_limit: str | None
    limitations: tuple[str, ...]


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


class ResearchDataGapsView(BaseModel):
    research_run_id: str
    status: str
    validation_disposition: str
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: Confidence
    issue_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    declared_unknown_count: int = Field(ge=0)
    issues: tuple[ValidationIssueView, ...]
    declared_unknowns: tuple[str, ...]
    limitations: tuple[str, ...]


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


class EvidenceBackedSupplierOfferView(SupplierOfferRankingView):
    product_name: str
    original_amount: Decimal
    original_currency: str
    quoted_quantity: int
    unit: str
    minimum_order_quantity: int | None
    incoterm: str | None
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    evidence_classification: str
    evidence_confidence: Confidence
    transformation: str | None

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def normalize_naive_database_retrieval_time(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class SupplierEvidenceCoverageView(BaseModel):
    supplier_name: str
    observation_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    offer_count: int = Field(ge=1)
    distinct_source_count: int = Field(ge=1)
    moq_observation_count: int = Field(ge=0)
    incoterm_observation_count: int = Field(ge=0)
    rankable_offer_count: int = Field(ge=0)
    unknown_factors: tuple[str, ...]
    due_diligence_status: str


class SupplierCoverageSummaryView(BaseModel):
    status: str
    suppliers: tuple[SupplierEvidenceCoverageView, ...]
    unidentified_observation_ids: tuple[str, ...]
    limitations: tuple[str, ...]


class EvidenceBackedPriceObservationView(BaseModel):
    external_observation_id: str
    product_name: str
    product_variant: str | None
    product_attributes: dict[str, str]
    supplier_name: str | None
    original_amount: Decimal
    original_currency: str
    quoted_quantity: int
    unit: str
    minimum_order_quantity: int | None
    incoterm: str | None
    market_layer: str
    normalized_amount: Decimal | None
    normalized_currency: str | None
    comparison_group: str
    product_match_classification: str
    product_match_score: int = Field(ge=0, le=100)
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    evidence_classification: str
    evidence_confidence: Confidence
    transformation: str | None

    @field_validator("retrieved_at", mode="before")
    @classmethod
    def normalize_naive_database_retrieval_time(cls, value: Any) -> Any:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class QuantityTierPointView(BaseModel):
    observation_id: str
    quoted_quantity: int
    minimum_order_quantity: int | None
    eligible_for_requested_quantity: bool
    original_amount: Decimal
    original_currency: str
    normalized_amount: Decimal | None
    normalized_currency: str | None
    normalized_change_from_previous_percent: Decimal | None
    source_name: str
    source_url: str


class QuantityOfferSeriesView(BaseModel):
    supplier_name: str | None
    product_name: str
    product_variant: str | None
    comparison_group: str
    points: tuple[QuantityTierPointView, ...]


class QuantityAnalysisView(BaseModel):
    status: str
    requested_quantity: int
    series: tuple[QuantityOfferSeriesView, ...]
    economic_order_range_min: int | None
    economic_order_range_max: int | None
    limitations: tuple[str, ...]


class PriceDistributionGroupView(BaseModel):
    product_name: str
    product_variant: str | None
    market_layer: str
    comparison_group: str
    quoted_quantity: int
    normalized_currency: str
    observation_ids: tuple[str, ...]
    observation_count: int
    distinct_source_count: int
    minimum_amount: Decimal
    median_amount: Decimal
    maximum_amount: Decimal
    range_amount: Decimal


class PriceDistributionView(BaseModel):
    status: str
    groups: tuple[PriceDistributionGroupView, ...]
    excluded_observation_ids: tuple[str, ...]
    limitations: tuple[str, ...]


class LandedCostScenarioView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    quantity: int
    target_currency: str
    total_amount: Decimal
    per_unit_amount: Decimal


class LandedCostComponentView(BaseModel):
    code: str
    label_fa: str
    amount: Decimal
    currency: str
    evidence_class: str
    formula: str


class LandedCostScenarioDetailView(LandedCostScenarioView):
    components: list[LandedCostComponentView]


class ScenarioSensitivityView(BaseModel):
    status: str
    quantity: int | None
    target_currency: str | None
    optimistic_per_unit: Decimal | None
    base_per_unit: Decimal | None
    conservative_per_unit: Decimal | None
    optimistic_delta_from_base: Decimal | None
    optimistic_delta_percent: Decimal | None
    conservative_delta_from_base: Decimal | None
    conservative_delta_percent: Decimal | None
    range_per_unit: Decimal | None
    range_percent_of_base: Decimal | None
    limitations: tuple[str, ...]


class LandedCostLedgerView(BaseModel):
    research_run_id: str
    scenarios: list[LandedCostScenarioDetailView]
    scenario_sensitivity: ScenarioSensitivityView


class ResearchAssumptionsView(BaseModel):
    research_run_id: str
    assumptions: list[str]
    unknowns: list[str]


class DecisionReportView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_run_id: str
    case_id: str
    format: str
    content: str
    content_sha256: str
    generated_at: datetime


class OpportunityDecisionView(BaseModel):
    opportunity_id: str
    research_run: ResearchRunView
    validation: ResearchValidationView
    scenarios: list[LandedCostScenarioView]
    scenario_sensitivity: ScenarioSensitivityView
    assumptions: list[str]
    unknowns: list[str]
    leading_offers: list[EvidenceBackedSupplierOfferView]
    report: DecisionReportView


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
