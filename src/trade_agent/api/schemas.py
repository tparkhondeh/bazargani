from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from trade_agent.application.reference_rates import ProviderRuntimeHealthStatus
from trade_agent.domain.models import SAFE_SUPPLIER_IDENTITY_CLAIM_ID_PATTERN, Confidence
from trade_agent.domain.workflow import (
    OpportunityStatus,
    ResearchReviewDecision,
    ResearchRunStatus,
    SupplierIdentityReviewDecision,
    SupplierIdentityReviewStatus,
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
    supersedes_research_run_id: str | None
    recalculation_reason: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ResearchRunPageView(BaseModel):
    items: list[ResearchRunView]
    next_cursor: str | None


class SuccessorResearchRunCreate(BaseModel):
    expected_version: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=2_000)


class SuccessorResearchRunView(ResearchRunView):
    supersedes_research_run_id: str
    recalculation_reason: str
    idempotency_replayed: bool


class _ResearchReviewAuditPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision: ResearchReviewDecision
    previous_status: ResearchRunStatus = Field(alias="from")
    resulting_status: ResearchRunStatus = Field(alias="to")
    version: int = Field(gt=0, strict=True)


class _SupplierIdentityReviewAuditPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    research_run_id: UUID
    claim_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=SAFE_SUPPLIER_IDENTITY_CLAIM_ID_PATTERN,
    )
    decision: SupplierIdentityReviewDecision
    previous_version: int = Field(ge=0, strict=True)
    resulting_version: int = Field(gt=0, strict=True)


_PUBLIC_REVIEW_AUDIT_MODELS: dict[str, type[BaseModel]] = {
    "REVIEW_RECORDED": _ResearchReviewAuditPayload,
    "IDENTITY_CLAIM_REVIEW_RECORDED": _SupplierIdentityReviewAuditPayload,
}


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

    @model_validator(mode="after")
    def enforce_public_review_payload_contract(self) -> AuditEventView:
        payload_model = _PUBLIC_REVIEW_AUDIT_MODELS.get(self.action)
        if payload_model is not None:
            try:
                validated = payload_model.model_validate(self.payload)
            except ValidationError:
                self.payload = {}
            else:
                self.payload = validated.model_dump(mode="json", by_alias=True)
        return self


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


class ResearchReviewQueueItemView(BaseModel):
    research_run_id: str
    opportunity_id: str
    product_name: str
    opportunity_quantity: int = Field(gt=0)
    target_market: str
    opportunity_status: OpportunityStatus
    next_action: str | None
    deadline: AwareDatetime | None
    supersedes_research_run_id: str | None
    research_status: ResearchRunStatus
    expected_version: int = Field(gt=0)
    run_created_at: AwareDatetime
    run_updated_at: AwareDatetime
    validation_policy_version: str
    validation_disposition: str
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: Confidence
    validation_evaluated_at: AwareDatetime
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_generated_at: AwareDatetime
    data_gap_status: str
    data_gap_issue_count: int = Field(ge=0)
    data_gap_error_count: int = Field(ge=0)
    data_gap_warning_count: int = Field(ge=0)
    declared_unknown_count: int = Field(ge=0)


class ResearchReviewQueuePageView(BaseModel):
    items: list[ResearchReviewQueueItemView]
    included_statuses: tuple[
        Literal["NEEDS_VERIFICATION", "NEEDS_HUMAN_REVIEW", "PARTIAL"], ...
    ]
    next_cursor: str | None
    limitations: tuple[str, ...]


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


class EvidenceFreshnessItemView(BaseModel):
    evidence_id: str
    fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: str
    confidence: Confidence
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    age_seconds: Decimal
    usage_count: int = Field(ge=0)
    freshness_status: str


class EvidenceFreshnessSummaryView(BaseModel):
    status: str
    validation_policy_version: str
    evaluated_at: AwareDatetime
    max_age_seconds: int = Field(gt=0)
    future_clock_skew_seconds: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    current_count: int = Field(ge=0)
    within_clock_skew_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    future_dated_count: int = Field(ge=0)
    items: tuple[EvidenceFreshnessItemView, ...]
    limitations: tuple[str, ...]


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
    terms_approved: bool
    supported_scope: tuple[str, ...]
    fixed_hosts: tuple[str, ...]
    cache_ttl_seconds: int
    declared_rate_limit: str | None
    limitations: tuple[str, ...]


class ProviderRuntimeHealthView(BaseModel):
    provider_id: str
    enabled: bool
    status: ProviderRuntimeHealthStatus
    observation_scope: Literal["PROCESS_LOCAL"]
    observed_since: AwareDatetime
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    last_failure_at: AwareDatetime | None
    upstream_attempt_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    consecutive_failure_count: int = Field(ge=0)
    cache_hit_count: int = Field(ge=0)
    endpoint_probe_performed: Literal[False]
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
    supplier_identity_claim_count: int = Field(default=0, ge=0)


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
    incoterm_named_place: str | None
    incoterm_version: str | None
    payment_terms: str | None
    payment_method: str | None
    quote_valid_until: AwareDatetime | None
    lead_time_days: int | None
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    evidence_classification: str
    evidence_confidence: Confidence
    transformation: str | None

    @field_validator("retrieved_at", "quote_valid_until", mode="before")
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


class SupplierIdentityClaimView(BaseModel):
    claim_id: str
    observation_id: str
    quoted_supplier_name: str | None
    claimed_legal_name: str
    jurisdiction: str
    registration_number: str
    review_status: SupplierIdentityReviewStatus
    review_version: int = Field(ge=0)
    latest_reviewed_at: AwareDatetime | None
    source_name: str
    source_url: str
    retrieved_at: AwareDatetime
    evidence_classification: str
    evidence_confidence: Confidence
    transformation: str | None


class SupplierIdentityClaimSummaryView(BaseModel):
    research_run_id: str
    status: Literal[
        "NO_SUPPLIER_IDENTITY_CLAIMS",
        "REVIEWED_IDENTITY_CLAIMS",
        "UNREVIEWED_IDENTITY_CLAIMS",
    ]
    claim_count: int = Field(ge=0)
    claims: tuple[SupplierIdentityClaimView, ...]
    limitations: tuple[str, ...]


class SupplierIdentityClaimReviewSubmit(BaseModel):
    decision: SupplierIdentityReviewDecision
    rationale: str = Field(min_length=3, max_length=2_000)
    expected_version: int = Field(ge=0)


class SupplierIdentityClaimReviewView(BaseModel):
    id: str
    research_run_id: str
    claim_id: str
    reviewer_actor_id: str
    decision: SupplierIdentityReviewDecision
    rationale: str
    previous_status: SupplierIdentityReviewStatus
    resulting_status: SupplierIdentityReviewStatus
    previous_version: int = Field(ge=0)
    resulting_version: int = Field(gt=0)
    created_at: AwareDatetime


class SupplierIdentityReviewQueueItemView(SupplierIdentityClaimView):
    research_run_id: str
    opportunity_id: str
    product_name: str
    opportunity_quantity: int = Field(gt=0)
    target_market: str
    claim_created_at: AwareDatetime


class SupplierIdentityReviewQueuePageView(BaseModel):
    items: list[SupplierIdentityReviewQueueItemView]
    included_statuses: tuple[Literal["UNREVIEWED", "INCONCLUSIVE"], ...]
    next_cursor: str | None
    limitations: tuple[str, ...]


class IncotermEvidenceGroupView(BaseModel):
    code: str
    recognized: bool
    observation_ids: tuple[str, ...]
    supplier_names: tuple[str, ...]
    source_urls: tuple[str, ...]
    named_places: tuple[str, ...]
    declared_versions: tuple[str, ...]
    offer_count: int = Field(ge=1)
    named_supplier_count: int = Field(ge=0)
    distinct_source_count: int = Field(ge=1)
    named_place_observation_count: int = Field(ge=0)
    version_observation_count: int = Field(ge=0)
    complete_terms_observation_count: int = Field(ge=0)


class IncotermCoverageSummaryView(BaseModel):
    status: str
    reference_version: str
    reference_codes: tuple[str, ...]
    observed_recognized_codes: tuple[str, ...]
    unrecognized_declared_codes: tuple[str, ...]
    groups: tuple[IncotermEvidenceGroupView, ...]
    missing_incoterm_observation_ids: tuple[str, ...]
    missing_named_place_observation_ids: tuple[str, ...]
    missing_version_observation_ids: tuple[str, ...]
    comparison_status: str
    limitations: tuple[str, ...]


class OfferTermsCoverageView(BaseModel):
    observation_id: str
    supplier_name: str | None
    declared_fields: tuple[str, ...]
    missing_recorded_fields: tuple[str, ...]
    declared_recorded_field_count: int = Field(ge=0)
    rankable: bool
    ranking_unknown_factors: tuple[str, ...]


class OfferTermsCoverageSummaryView(BaseModel):
    status: str
    recorded_core_term_fields: tuple[str, ...]
    offers: tuple[OfferTermsCoverageView, ...]
    uncaptured_commercial_term_fields: tuple[str, ...]
    limitations: tuple[str, ...]


class ExecutiveSupplierCandidateView(BaseModel):
    observation_id: str
    supplier_name: str
    original_amount: Decimal
    original_currency: str
    normalized_amount: Decimal
    normalized_currency: str
    total_score: int = Field(ge=0, le=100)
    source_url: str
    evidence_classification: str
    evidence_confidence: str
    due_diligence_status: str


class ExecutiveDecisionSummaryView(BaseModel):
    decision_status: str
    recommendation_code: str
    supplier_candidate_status: str
    leading_supplier_candidates: tuple[ExecutiveSupplierCandidateView, ...]
    base_landed_cost_per_unit: Decimal
    base_landed_cost_currency: str
    iran_market_benchmark_status: str
    iran_market_unit_price: Decimal | None
    potential_gross_spread_per_unit: Decimal | None
    potential_gross_spread_percent: Decimal | None
    data_gap_status: str
    data_gap_issue_count: int = Field(ge=0)
    declared_unknown_count: int = Field(ge=0)
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: str
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
    incoterm_named_place: str | None
    incoterm_version: str | None
    payment_terms: str | None
    payment_method: str | None
    quote_valid_until: AwareDatetime | None
    lead_time_days: int | None
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

    @field_validator("retrieved_at", "quote_valid_until", mode="before")
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


class ScenarioCostCoverageView(BaseModel):
    name: str
    recorded_component_codes: tuple[str, ...]
    recognized_reference_codes: tuple[str, ...]
    unrecorded_reference_codes: tuple[str, ...]
    unclassified_component_codes: tuple[str, ...]
    zero_amount_codes: tuple[str, ...]
    recorded_component_count: int = Field(ge=0)
    fact_count: int = Field(ge=0)
    estimate_count: int = Field(ge=0)
    assumption_count: int = Field(ge=0)
    derived_calculation_count: int = Field(ge=0)
    ai_inference_count: int = Field(ge=0)


class TradeCostCoverageView(BaseModel):
    status: str
    reference_component_codes: tuple[str, ...]
    scenarios: tuple[ScenarioCostCoverageView, ...]
    limitations: tuple[str, ...]


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
    executive_summary: ExecutiveDecisionSummaryView
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
