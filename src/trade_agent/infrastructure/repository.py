from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from trade_agent.application.cost_coverage import (
    CostCoveragePoint,
    ScenarioCostCoverageInput,
    analyze_trade_cost_coverage,
)
from trade_agent.application.data_gaps import DataGapIssue, summarize_data_gaps
from trade_agent.application.evidence_freshness import (
    EvidenceFreshnessPoint,
    analyze_evidence_freshness,
    evidence_fingerprint_sha256,
)
from trade_agent.application.executive_summary import (
    ExecutiveSupplierCandidate,
    build_executive_summary,
)
from trade_agent.application.incoterm_coverage import (
    IncotermEvidencePoint,
    summarize_incoterm_coverage,
)
from trade_agent.application.matching import normalize_product_text
from trade_agent.application.offer_terms_coverage import (
    OfferTermsPoint,
    summarize_offer_terms_coverage,
)
from trade_agent.application.pagination import PageCursor, encode_cursor
from trade_agent.application.ports import ResearchCompletion
from trade_agent.application.price_distribution import (
    DistributionPricePoint,
    analyze_price_distribution,
)
from trade_agent.application.quantity import (
    QuantityPricePoint,
    analyze_quantity_points,
    quantity_product_key,
)
from trade_agent.application.research import ResearchResult
from trade_agent.application.sensitivity import (
    ScenarioCostPoint,
    analyze_scenario_sensitivity,
)
from trade_agent.application.supplier_coverage import (
    SupplierEvidencePoint,
    summarize_supplier_coverage,
)
from trade_agent.application.supplier_identity import (
    SupplierIdentityClaimPoint,
    summarize_supplier_identity_claims,
)
from trade_agent.application.validation import ValidationDisposition
from trade_agent.domain.errors import PublicInputError
from trade_agent.domain.models import Evidence
from trade_agent.domain.workflow import (
    IdempotencyConflictError,
    InvalidTransitionError,
    OpportunityStatus,
    ResearchReviewDecision,
    ResearchRunStatus,
    VersionConflictError,
    ensure_manual_research_transition,
    ensure_opportunity_transition,
    review_target_status,
)
from trade_agent.infrastructure.database import (
    AuditEventRecord,
    DecisionReportRecord,
    EvidenceRecord,
    FXRateRecord,
    IdempotencyRecord,
    LandedCostComponentRecord,
    LandedCostScenarioRecord,
    OpportunityRecord,
    PriceObservationRecord,
    ProductMatchRecord,
    ResearchNoteRecord,
    ResearchReviewRecord,
    ResearchRunRecord,
    ResearchValidationRecord,
    SourceRecord,
    SupplierIdentityClaimRecord,
    SupplierOfferRankingRecord,
    ValidationIssueRecord,
)


def _database_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class TradeRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_opportunity(
        self,
        *,
        product_name: str,
        quantity: int,
        target_market: str,
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> OpportunityRecord:
        if quantity <= 0:
            raise PublicInputError("quantity must be positive")
        now = datetime.now(UTC)
        record = OpportunityRecord(
            id=str(uuid4()),
            tenant_id=tenant_id,
            product_name=product_name.strip(),
            quantity=quantity,
            target_market=target_market.strip(),
            status=OpportunityStatus.RESEARCHING.value,
            created_at=now,
            updated_at=now,
        )
        if not record.product_name or not record.target_market:
            raise PublicInputError("product_name and target_market are required")
        with self._session_factory.begin() as session:
            session.add(record)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "Opportunity",
                record.id,
                "CREATED",
                {},
            )
        return record

    def get_opportunity(self, opportunity_id: str, *, tenant_id: str) -> OpportunityRecord:
        with self._session_factory() as session:
            record = session.scalar(
                select(OpportunityRecord).where(
                    OpportunityRecord.id == opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                raise KeyError("opportunity not found")
            session.expunge(record)
            return record

    def transition_opportunity(
        self,
        *,
        opportunity_id: str,
        target: OpportunityStatus,
        expected_version: int,
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> OpportunityRecord:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(OpportunityRecord)
                .where(
                    OpportunityRecord.id == opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if record is None:
                raise KeyError("opportunity not found")
            if record.version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current version {record.version}"
                )
            current = OpportunityStatus(record.status)
            ensure_opportunity_transition(current, target)
            record.status = target.value
            record.version += 1
            record.updated_at = datetime.now(UTC)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "Opportunity",
                record.id,
                "STATUS_CHANGED",
                {"from": current.value, "to": target.value, "version": record.version},
            )
        return record

    def update_opportunity_context(
        self,
        *,
        opportunity_id: str,
        expected_version: int,
        changes: dict[str, str | datetime | None],
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> OpportunityRecord:
        allowed_fields = frozenset({"next_action", "deadline", "notes"})
        if not changes or not changes.keys() <= allowed_fields:
            raise PublicInputError("at least one opportunity context field is required")

        normalized: dict[str, str | datetime | None] = {}
        for field, value in changes.items():
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    raise PublicInputError(f"{field} cannot be blank")
            if field == "deadline" and isinstance(value, datetime):
                value = value.astimezone(UTC)
            normalized[field] = value

        with self._session_factory.begin() as session:
            record = session.scalar(
                select(OpportunityRecord)
                .where(
                    OpportunityRecord.id == opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if record is None:
                raise KeyError("opportunity not found")
            if record.version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current version {record.version}"
                )
            for field, value in normalized.items():
                setattr(record, field, value)
            record.version += 1
            record.updated_at = datetime.now(UTC)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "Opportunity",
                record.id,
                "CONTEXT_UPDATED",
                {"fields": sorted(normalized), "version": record.version},
            )
        return record

    def list_opportunities(
        self,
        *,
        tenant_id: str,
        status: OpportunityStatus | None,
        limit: int,
        after: PageCursor | None,
    ) -> tuple[list[OpportunityRecord], str | None]:
        if not 1 <= limit <= 100:
            raise PublicInputError("page limit must be between 1 and 100")
        with self._session_factory() as session:
            statement = select(OpportunityRecord).where(
                OpportunityRecord.tenant_id == tenant_id
            )
            if status is not None:
                statement = statement.where(OpportunityRecord.status == status.value)
            if after is not None:
                statement = statement.where(
                    or_(
                        OpportunityRecord.created_at < after.created_at,
                        and_(
                            OpportunityRecord.created_at == after.created_at,
                            OpportunityRecord.id < after.record_id,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    statement.order_by(
                        OpportunityRecord.created_at.desc(),
                        OpportunityRecord.id.desc(),
                    ).limit(limit + 1)
                )
            )
            has_more = len(records) > limit
            page = records[:limit]
            next_cursor = (
                encode_cursor(page[-1].created_at, page[-1].id)
                if has_more and page
                else None
            )
            for record in page:
                session.expunge(record)
            return page, next_cursor

    def list_audit_events(
        self,
        *,
        tenant_id: str,
        limit: int,
        after: PageCursor | None,
    ) -> tuple[list[AuditEventRecord], str | None]:
        if not 1 <= limit <= 100:
            raise PublicInputError("page limit must be between 1 and 100")
        with self._session_factory() as session:
            statement = select(AuditEventRecord).where(
                AuditEventRecord.tenant_id == tenant_id
            )
            if after is not None:
                statement = statement.where(
                    or_(
                        AuditEventRecord.occurred_at < after.created_at,
                        and_(
                            AuditEventRecord.occurred_at == after.created_at,
                            AuditEventRecord.id < after.record_id,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    statement.order_by(
                        AuditEventRecord.occurred_at.desc(),
                        AuditEventRecord.id.desc(),
                    ).limit(limit + 1)
                )
            )
            has_more = len(records) > limit
            page = records[:limit]
            next_cursor = (
                encode_cursor(page[-1].occurred_at, page[-1].id)
                if has_more and page
                else None
            )
            for record in page:
                session.expunge(record)
            return page, next_cursor

    def create_research_run(
        self,
        *,
        opportunity_id: str,
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> ResearchRunRecord:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            opportunity = session.scalar(
                select(OpportunityRecord).where(
                    OpportunityRecord.id == opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
            )
            if opportunity is None:
                raise KeyError("opportunity not found")
            record = ResearchRunRecord(
                id=str(uuid4()),
                tenant_id=tenant_id,
                opportunity_id=opportunity_id,
                status=ResearchRunStatus.CREATED.value,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "ResearchRun",
                record.id,
                "CREATED",
                {},
            )
        return record

    def list_research_runs(
        self,
        *,
        opportunity_id: str,
        tenant_id: str,
        limit: int,
        after: PageCursor | None,
    ) -> tuple[list[ResearchRunRecord], str | None]:
        if not 1 <= limit <= 100:
            raise PublicInputError("page limit must be between 1 and 100")
        with self._session_factory() as session:
            opportunity = session.scalar(
                select(OpportunityRecord.id).where(
                    OpportunityRecord.id == opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
            )
            if opportunity is None:
                raise KeyError("opportunity not found")
            statement = select(ResearchRunRecord).where(
                ResearchRunRecord.opportunity_id == opportunity_id,
                ResearchRunRecord.tenant_id == tenant_id,
            )
            if after is not None:
                statement = statement.where(
                    or_(
                        ResearchRunRecord.created_at < after.created_at,
                        and_(
                            ResearchRunRecord.created_at == after.created_at,
                            ResearchRunRecord.id < after.record_id,
                        ),
                    )
                )
            records = list(
                session.scalars(
                    statement.order_by(
                        ResearchRunRecord.created_at.desc(),
                        ResearchRunRecord.id.desc(),
                    ).limit(limit + 1)
                )
            )
            has_more = len(records) > limit
            page = records[:limit]
            next_cursor = (
                encode_cursor(page[-1].created_at, page[-1].id)
                if has_more and page
                else None
            )
            for record in page:
                session.expunge(record)
            return page, next_cursor

    def transition_research_run(
        self,
        *,
        run_id: str,
        target: ResearchRunStatus,
        expected_version: int,
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> ResearchRunRecord:
        with self._session_factory.begin() as session:
            statement = (
                select(ResearchRunRecord)
                .where(
                    ResearchRunRecord.id == run_id,
                    ResearchRunRecord.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            record = session.scalar(statement)
            if record is None:
                raise KeyError("research run not found")
            if record.version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current version {record.version}"
                )
            current = ResearchRunStatus(record.status)
            ensure_manual_research_transition(current, target)
            record.status = target.value
            record.version += 1
            record.updated_at = datetime.now(UTC)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "ResearchRun",
                record.id,
                "STATUS_CHANGED",
                {"from": current.value, "to": target.value, "version": record.version},
            )
        return record

    def record_research_review(
        self,
        *,
        run_id: str,
        decision: ResearchReviewDecision,
        rationale: str,
        expected_version: int,
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
    ) -> ResearchReviewRecord:
        normalized_rationale = rationale.strip()
        if not 3 <= len(normalized_rationale) <= 2_000:
            raise PublicInputError("review rationale must contain 3 to 2000 characters")
        with self._session_factory.begin() as session:
            run = session.scalar(
                select(ResearchRunRecord)
                .where(
                    ResearchRunRecord.id == run_id,
                    ResearchRunRecord.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if run is None:
                raise KeyError("research run not found")
            if run.version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current version {run.version}"
                )
            current = ResearchRunStatus(run.status)
            target = review_target_status(current, decision)
            review = ResearchReviewRecord(
                id=str(uuid4()),
                tenant_id=tenant_id,
                research_run_id=run_id,
                reviewer_actor_id=actor_id,
                decision=decision.value,
                rationale=normalized_rationale,
                previous_status=current.value,
                resulting_status=target.value,
                previous_version=run.version,
                resulting_version=run.version + 1,
                created_at=datetime.now(UTC),
            )
            run.status = target.value
            run.version += 1
            run.updated_at = datetime.now(UTC)
            session.add(review)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "ResearchRun",
                run.id,
                "REVIEW_RECORDED",
                {
                    "decision": decision.value,
                    "rationale": normalized_rationale,
                    "from": current.value,
                    "to": target.value,
                    "version": run.version,
                },
            )
        return review

    def get_research_reviews(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> list[ResearchReviewRecord]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            records = list(
                session.scalars(
                    select(ResearchReviewRecord)
                    .where(
                        ResearchReviewRecord.research_run_id == run_id,
                        ResearchReviewRecord.tenant_id == tenant_id,
                    )
                    .order_by(ResearchReviewRecord.created_at, ResearchReviewRecord.id)
                )
            )
            for record in records:
                session.expunge(record)
            return records

    def persist_research_result(
        self,
        *,
        run_id: str,
        result: ResearchResult,
        report_markdown: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
        tenant_id: str,
        actor_id: str,
    ) -> ResearchCompletion:
        scope = f"research-result:{tenant_id}:{run_id}"
        try:
            return self._persist_research_result_once(
                run_id=run_id,
                result=result,
                report_markdown=report_markdown,
                expected_version=expected_version,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                scope=scope,
                tenant_id=tenant_id,
                actor_id=actor_id,
            )
        except IntegrityError:
            replay = self._load_idempotent_completion(
                scope=scope,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                tenant_id=tenant_id,
            )
            if replay is None:
                raise
            return replay

    def replay_research_result(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        request_hash: str,
        tenant_id: str,
    ) -> ResearchCompletion | None:
        return self._load_idempotent_completion(
            scope=f"research-result:{tenant_id}:{run_id}",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            tenant_id=tenant_id,
        )

    def _persist_research_result_once(
        self,
        *,
        run_id: str,
        result: ResearchResult,
        report_markdown: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
        scope: str,
        tenant_id: str,
        actor_id: str,
    ) -> ResearchCompletion:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise PublicInputError("idempotency_key must contain 1 to 128 characters")
        with self._session_factory.begin() as session:
            idempotency = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                    IdempotencyRecord.tenant_id == tenant_id,
                )
            )
            if idempotency is not None:
                return self._completion_from_idempotency(idempotency, request_hash)
            statement = (
                select(ResearchRunRecord)
                .where(
                    ResearchRunRecord.id == run_id,
                    ResearchRunRecord.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            run = session.scalar(statement)
            if run is None:
                raise KeyError("research run not found")
            if run.version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current version {run.version}"
                )
            if ResearchRunStatus(run.status) is not ResearchRunStatus.RUNNING:
                raise InvalidTransitionError("research results require a RUNNING research run")
            existing_report = session.scalar(
                select(DecisionReportRecord).where(DecisionReportRecord.research_run_id == run_id)
            )
            if existing_report is not None:
                raise VersionConflictError("research results are append-only and already exist")

            opportunity = session.scalar(
                select(OpportunityRecord).where(
                    OpportunityRecord.id == run.opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
            )
            if opportunity is None:
                raise KeyError("opportunity not found")
            if opportunity.quantity != result.case.quantity:
                raise PublicInputError("bundle quantity does not match the opportunity")
            if normalize_product_text(opportunity.product_name) != normalize_product_text(
                result.case.product_name
            ):
                raise PublicInputError("bundle product_name does not match the opportunity")
            if normalize_product_text(opportunity.target_market) != normalize_product_text(
                result.case.destination
            ):
                raise PublicInputError("bundle destination does not match the opportunity")

            evidence_cache: dict[str, EvidenceRecord] = {}
            observation_records: dict[str, PriceObservationRecord] = {}
            for observation in result.case.observations:
                evidence = self._evidence(session, run_id, observation.evidence, evidence_cache)
                observation_record = PriceObservationRecord(
                    id=str(uuid4()),
                    research_run_id=run_id,
                    evidence_id=evidence.id,
                    external_observation_id=observation.observation_id,
                    product_name=observation.product_name,
                    supplier_name=observation.supplier_name,
                    original_amount=observation.unit_price.amount,
                    original_currency=observation.unit_price.currency,
                    quantity=observation.quantity,
                    unit=observation.unit,
                    minimum_order_quantity=observation.minimum_order_quantity,
                    incoterm=observation.incoterm,
                    incoterm_named_place=observation.incoterm_named_place,
                    incoterm_version=observation.incoterm_version,
                    payment_terms=observation.payment_terms,
                    payment_method=observation.payment_method,
                    quote_valid_until=observation.quote_valid_until,
                    lead_time_days=observation.lead_time_days,
                    product_variant=observation.product_variant,
                    product_attributes=observation.product_attributes,
                    market_layer=observation.market_layer,
                )
                session.add(observation_record)
                observation_records[observation.observation_id] = observation_record

            for match in result.product_matches:
                matched_observation_record = observation_records.get(match.observation_id)
                if matched_observation_record is None:
                    raise ValueError(
                        f"product match references unknown observation: {match.observation_id}"
                    )
                session.add(
                    ProductMatchRecord(
                        id=str(uuid4()),
                        research_run_id=run_id,
                        price_observation_id=matched_observation_record.id,
                        external_observation_id=match.observation_id,
                        classification=match.classification.value,
                        score=match.score,
                        name_similarity=match.name_similarity,
                        requested_attributes=match.requested_attributes,
                        observed_attributes=match.observed_attributes,
                        matched_attributes=list(match.matched_attributes),
                        conflicting_attributes=list(match.conflicting_attributes),
                        missing_attributes=list(match.missing_attributes),
                        explanation_fa=list(match.explanation_fa),
                        policy_version=match.policy_version,
                    )
                )

            for ranking in result.supplier_rankings:
                ranked_observation_record = observation_records.get(ranking.observation_id)
                if ranked_observation_record is None:
                    raise ValueError(
                        f"supplier ranking references unknown observation: {ranking.observation_id}"
                    )
                normalized = ranking.normalized_unit_price
                session.add(
                    SupplierOfferRankingRecord(
                        id=str(uuid4()),
                        research_run_id=run_id,
                        price_observation_id=ranked_observation_record.id,
                        external_observation_id=ranking.observation_id,
                        supplier_name=ranking.supplier_name,
                        comparison_group=ranking.comparison_group,
                        rank=ranking.rank,
                        eligible_for_quantity=ranking.eligible_for_quantity,
                        rankable=ranking.rankable,
                        normalized_amount=normalized.amount if normalized else None,
                        normalized_currency=normalized.currency if normalized else None,
                        total_score=ranking.total_score,
                        component_scores=ranking.component_scores,
                        unknown_factors=list(ranking.unknown_factors),
                        explanation_fa=list(ranking.explanation_fa),
                        policy_version=ranking.policy_version,
                    )
                )

            for claim in result.case.supplier_identity_claims:
                claimed_observation_record = observation_records.get(claim.observation_id)
                if claimed_observation_record is None:
                    raise ValueError(
                        "supplier identity claim references unknown observation: "
                        f"{claim.observation_id}"
                    )
                evidence = self._evidence(
                    session,
                    run_id,
                    claim.evidence,
                    evidence_cache,
                )
                session.add(
                    SupplierIdentityClaimRecord(
                        id=str(uuid4()),
                        research_run_id=run_id,
                        price_observation_id=claimed_observation_record.id,
                        evidence_id=evidence.id,
                        external_claim_id=claim.claim_id,
                        claimed_legal_name=claim.claimed_legal_name,
                        jurisdiction=claim.jurisdiction,
                        registration_number=claim.registration_number,
                        created_at=datetime.now(UTC),
                    )
                )

            scenario_records: dict[str, LandedCostScenarioRecord] = {}
            for scenario_result in result.scenarios:
                scenario_record = LandedCostScenarioRecord(
                    id=str(uuid4()),
                    research_run_id=run_id,
                    name=scenario_result.name.value,
                    quantity=scenario_result.quantity,
                    target_currency=scenario_result.target_currency,
                    total_amount=scenario_result.total.amount,
                    per_unit_amount=scenario_result.per_unit.amount,
                    created_at=datetime.now(UTC),
                )
                session.add(scenario_record)
                session.flush()
                scenario_records[scenario_result.name.value] = scenario_record
                seen_codes: set[str] = set()
                for component in scenario_result.components:
                    if component.code in seen_codes:
                        raise ValueError(
                            f"duplicate component code in {scenario_result.name}: {component.code}"
                        )
                    seen_codes.add(component.code)
                    session.add(
                        LandedCostComponentRecord(
                            id=str(uuid4()),
                            scenario_id=scenario_record.id,
                            code=component.code,
                            label_fa=component.label_fa,
                            amount=component.amount.amount,
                            currency=component.amount.currency,
                            evidence_class=component.evidence_class.value,
                            formula=component.formula,
                        )
                    )

            fx_rate_count = 0
            for scenario_input in result.case.scenarios:
                scenario_record = scenario_records[scenario_input.name.value]
                fx_keys: set[tuple[str, str, str, datetime | None]] = set()
                for rate in scenario_input.fx_rates:
                    key = (
                        rate.base_currency,
                        rate.quote_currency,
                        rate.rate_type,
                        rate.effective_at,
                    )
                    if key in fx_keys:
                        continue
                    fx_keys.add(key)
                    evidence = self._evidence(session, run_id, rate.evidence, evidence_cache)
                    session.add(
                        FXRateRecord(
                            id=str(uuid4()),
                            research_run_id=run_id,
                            scenario_id=scenario_record.id,
                            evidence_id=evidence.id,
                            base_currency=rate.base_currency,
                            quote_currency=rate.quote_currency,
                            rate=rate.rate,
                            rate_type=rate.rate_type,
                            effective_at=rate.effective_at,
                        )
                    )
                    fx_rate_count += 1

            for kind, notes in (
                ("ASSUMPTION", result.case.assumptions),
                ("UNKNOWN", result.case.unknowns),
            ):
                for note in notes:
                    session.add(
                        ResearchNoteRecord(
                            id=str(uuid4()), research_run_id=run_id, kind=kind, text=note
                        )
                    )

            validation = result.validation
            session.add(
                ResearchValidationRecord(
                    id=str(uuid4()),
                    research_run_id=run_id,
                    policy_version=validation.policy_version,
                    disposition=validation.disposition.value,
                    confidence_score=validation.confidence_score,
                    confidence_label=validation.confidence_label.value,
                    evaluated_at=validation.evaluated_at,
                )
            )
            for issue in validation.issues:
                session.add(
                    ValidationIssueRecord(
                        id=str(uuid4()),
                        research_run_id=run_id,
                        code=issue.code,
                        severity=issue.severity.value,
                        message_fa=issue.message_fa,
                        subject_type=issue.subject_type,
                        subject_id=issue.subject_id,
                        details=issue.details,
                    )
                )

            report_hash = hashlib.sha256(report_markdown.encode("utf-8")).hexdigest()
            session.add(
                DecisionReportRecord(
                    id=str(uuid4()),
                    research_run_id=run_id,
                    case_id=result.case.case_id,
                    format="MARKDOWN",
                    content=report_markdown,
                    content_sha256=report_hash,
                    generated_at=datetime.now(UTC),
                )
            )
            target_status = {
                ValidationDisposition.PASSED: ResearchRunStatus.COMPLETED,
                ValidationDisposition.NEEDS_VERIFICATION: ResearchRunStatus.NEEDS_VERIFICATION,
                ValidationDisposition.NEEDS_HUMAN_REVIEW: ResearchRunStatus.NEEDS_HUMAN_REVIEW,
            }[validation.disposition]
            run.status = target_status.value
            run.version += 1
            run.updated_at = datetime.now(UTC)
            self._audit(
                session,
                correlation_id,
                tenant_id,
                actor_id,
                "ResearchRun",
                run.id,
                "RESULTS_PERSISTED",
                {
                    "case_id": result.case.case_id,
                    "evidence_count": len(evidence_cache),
                    "price_observation_count": len(result.case.observations),
                    "product_match_count": len(result.product_matches),
                    "supplier_ranking_count": len(result.supplier_rankings),
                    "supplier_identity_claim_count": len(
                        result.case.supplier_identity_claims
                    ),
                    "fx_rate_count": fx_rate_count,
                    "scenario_count": len(result.scenarios),
                    "validation_disposition": validation.disposition.value,
                    "validation_issue_count": len(validation.issues),
                    "confidence_score": validation.confidence_score,
                    "confidence_label": validation.confidence_label.value,
                    "report_sha256": report_hash,
                    "version": run.version,
                },
            )

            completion = ResearchCompletion(
                research_run_id=run_id,
                status=target_status.value,
                version=expected_version + 1,
                evidence_count=len(evidence_cache),
                price_observation_count=len(result.case.observations),
                product_match_count=len(result.product_matches),
                supplier_ranking_count=len(result.supplier_rankings),
                fx_rate_count=fx_rate_count,
                scenario_count=len(result.scenarios),
                validation_disposition=validation.disposition.value,
                validation_issue_count=len(validation.issues),
                confidence_score=validation.confidence_score,
                confidence_label=validation.confidence_label.value,
                report_sha256=report_hash,
                idempotency_replayed=False,
                supplier_identity_claim_count=len(
                    result.case.supplier_identity_claims
                ),
            )
            session.add(
                IdempotencyRecord(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    scope=scope,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload=asdict(completion),
                    created_at=datetime.now(UTC),
                )
            )

        return completion

    def get_research_report(
        self, run_id: str, *, tenant_id: str
    ) -> DecisionReportRecord:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            report = session.scalar(
                select(DecisionReportRecord).where(DecisionReportRecord.research_run_id == run_id)
            )
            if report is None:
                raise KeyError("research report not found")
            session.expunge(report)
            return report

    def get_latest_opportunity_decision(
        self,
        opportunity_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            opportunity_exists = session.scalar(
                select(OpportunityRecord.id).where(
                    OpportunityRecord.id == opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
            )
            if opportunity_exists is None:
                raise KeyError("opportunity not found")

            run = session.scalar(
                select(ResearchRunRecord)
                .join(
                    DecisionReportRecord,
                    DecisionReportRecord.research_run_id == ResearchRunRecord.id,
                )
                .where(
                    ResearchRunRecord.opportunity_id == opportunity_id,
                    ResearchRunRecord.tenant_id == tenant_id,
                )
                .order_by(
                    ResearchRunRecord.created_at.desc(),
                    ResearchRunRecord.id.desc(),
                )
                .limit(1)
            )
            if run is None:
                raise KeyError("opportunity decision not found")

            report = session.scalar(
                select(DecisionReportRecord).where(
                    DecisionReportRecord.research_run_id == run.id
                )
            )
            validation = session.scalar(
                select(ResearchValidationRecord).where(
                    ResearchValidationRecord.research_run_id == run.id
                )
            )
            scenarios = list(
                session.scalars(
                    select(LandedCostScenarioRecord).where(
                        LandedCostScenarioRecord.research_run_id == run.id
                    )
                )
            )
            leading_rows = session.execute(
                select(
                    SupplierOfferRankingRecord,
                    PriceObservationRecord,
                    EvidenceRecord,
                    SourceRecord,
                )
                .join(
                    PriceObservationRecord,
                    PriceObservationRecord.id
                    == SupplierOfferRankingRecord.price_observation_id,
                )
                .join(
                    EvidenceRecord,
                    EvidenceRecord.id == PriceObservationRecord.evidence_id,
                )
                .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                .where(
                    SupplierOfferRankingRecord.research_run_id == run.id,
                    SupplierOfferRankingRecord.rank == 1,
                )
                .order_by(
                    SupplierOfferRankingRecord.comparison_group,
                    SupplierOfferRankingRecord.id,
                )
            ).all()
            leading_offers = [
                self._supplier_offer_view(ranking, observation, evidence, source)
                for ranking, observation, evidence, source in leading_rows
            ]
            if report is None or validation is None or not scenarios:
                raise KeyError("opportunity decision not found")

            scenario_order = {"OPTIMISTIC": 0, "BASE": 1, "CONSERVATIVE": 2}
            scenarios.sort(key=lambda item: (scenario_order.get(item.name, 99), item.id))
            sensitivity = analyze_scenario_sensitivity(
                tuple(
                    ScenarioCostPoint(
                        name=scenario.name,
                        quantity=scenario.quantity,
                        target_currency=scenario.target_currency,
                        per_unit_amount=scenario.per_unit_amount,
                    )
                    for scenario in scenarios
                )
            )
            issues = list(
                session.scalars(
                    select(ValidationIssueRecord)
                    .where(ValidationIssueRecord.research_run_id == run.id)
                    .order_by(ValidationIssueRecord.severity, ValidationIssueRecord.code)
                )
            )
            validation_view = {
                "research_run_id": run.id,
                "policy_version": validation.policy_version,
                "disposition": validation.disposition,
                "confidence_score": validation.confidence_score,
                "confidence_label": validation.confidence_label,
                "evaluated_at": validation.evaluated_at,
                "issues": [
                    {
                        "code": issue.code,
                        "severity": issue.severity,
                        "message_fa": issue.message_fa,
                        "subject_type": issue.subject_type,
                        "subject_id": issue.subject_id,
                        "details": issue.details,
                    }
                    for issue in issues
                ],
            }
            assumptions = list(
                session.scalars(
                    select(ResearchNoteRecord.text)
                    .where(
                        ResearchNoteRecord.research_run_id == run.id,
                        ResearchNoteRecord.kind == "ASSUMPTION",
                    )
                    .order_by(ResearchNoteRecord.text, ResearchNoteRecord.id)
                )
            )
            unknowns = list(
                session.scalars(
                    select(ResearchNoteRecord.text)
                    .where(
                        ResearchNoteRecord.research_run_id == run.id,
                        ResearchNoteRecord.kind == "UNKNOWN",
                    )
                    .order_by(ResearchNoteRecord.text, ResearchNoteRecord.id)
                )
            )
            gap_summary = summarize_data_gaps(
                tuple(
                    DataGapIssue(
                        code=issue.code,
                        severity=issue.severity,
                        message_fa=issue.message_fa,
                        subject_type=issue.subject_type,
                        subject_id=issue.subject_id,
                        details=issue.details,
                    )
                    for issue in issues
                ),
                tuple(unknowns),
            )
            executive_candidates = tuple(
                self._executive_supplier_candidate(ranking, observation, evidence)
                for ranking, observation, evidence, _source in leading_rows
            )
            base_scenario = next(item for item in scenarios if item.name == "BASE")
            executive_summary = build_executive_summary(
                validation_disposition=validation.disposition,
                confidence_score=validation.confidence_score,
                confidence_label=validation.confidence_label,
                base_landed_cost_per_unit=base_scenario.per_unit_amount,
                base_landed_cost_currency=base_scenario.target_currency,
                leading_supplier_candidates=executive_candidates,
                data_gap_status=gap_summary.status,
                data_gap_issue_count=gap_summary.issue_count,
                declared_unknown_count=gap_summary.declared_unknown_count,
            )
            for record in (run, report, *scenarios):
                session.expunge(record)
            return {
                "opportunity_id": opportunity_id,
                "research_run": run,
                "validation": validation_view,
                "scenarios": scenarios,
                "scenario_sensitivity": asdict(sensitivity),
                "assumptions": assumptions,
                "unknowns": unknowns,
                "leading_offers": leading_offers,
                "executive_summary": asdict(executive_summary),
                "report": report,
            }

    def get_research_validation(self, run_id: str, *, tenant_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            validation = session.scalar(
                select(ResearchValidationRecord).where(
                    ResearchValidationRecord.research_run_id == run_id
                )
            )
            if validation is None:
                raise KeyError("research validation not found")
            issues = session.scalars(
                select(ValidationIssueRecord)
                .where(ValidationIssueRecord.research_run_id == run_id)
                .order_by(ValidationIssueRecord.severity, ValidationIssueRecord.code)
            ).all()
            return {
                "research_run_id": run_id,
                "policy_version": validation.policy_version,
                "disposition": validation.disposition,
                "confidence_score": validation.confidence_score,
                "confidence_label": validation.confidence_label,
                "evaluated_at": validation.evaluated_at,
                "issues": [
                    {
                        "code": issue.code,
                        "severity": issue.severity,
                        "message_fa": issue.message_fa,
                        "subject_type": issue.subject_type,
                        "subject_id": issue.subject_id,
                        "details": issue.details,
                    }
                    for issue in issues
                ],
            }

    def get_research_data_gaps(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            validation = session.scalar(
                select(ResearchValidationRecord).where(
                    ResearchValidationRecord.research_run_id == run_id
                )
            )
            if validation is None:
                raise KeyError("research validation not found")
            issue_records = tuple(
                session.scalars(
                    select(ValidationIssueRecord).where(
                        ValidationIssueRecord.research_run_id == run_id
                    )
                )
            )
            unknowns = tuple(
                session.scalars(
                    select(ResearchNoteRecord.text).where(
                        ResearchNoteRecord.research_run_id == run_id,
                        ResearchNoteRecord.kind == "UNKNOWN",
                    )
                )
            )
            summary = summarize_data_gaps(
                tuple(
                    DataGapIssue(
                        code=issue.code,
                        severity=issue.severity,
                        message_fa=issue.message_fa,
                        subject_type=issue.subject_type,
                        subject_id=issue.subject_id,
                        details=issue.details,
                    )
                    for issue in issue_records
                ),
                unknowns,
            )
            return {
                "research_run_id": run_id,
                "validation_disposition": validation.disposition,
                "confidence_score": validation.confidence_score,
                "confidence_label": validation.confidence_label,
                **asdict(summary),
            }

    def get_landed_cost_scenarios(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            scenarios = list(
                session.scalars(
                    select(LandedCostScenarioRecord).where(
                        LandedCostScenarioRecord.research_run_id == run_id
                    )
                )
            )
            if not scenarios:
                raise KeyError("landed cost scenarios not found")

            scenario_order = {"OPTIMISTIC": 0, "BASE": 1, "CONSERVATIVE": 2}
            scenarios.sort(key=lambda item: (scenario_order.get(item.name, 99), item.id))
            scenario_ids = [scenario.id for scenario in scenarios]
            components = list(
                session.scalars(
                    select(LandedCostComponentRecord).where(
                        LandedCostComponentRecord.scenario_id.in_(scenario_ids)
                    )
                )
            )
            component_order = {"product_cost": 0, "unexpected_cost": 2}
            components.sort(
                key=lambda item: (
                    item.scenario_id,
                    component_order.get(item.code, 1),
                    item.code,
                    item.id,
                )
            )
            components_by_scenario: dict[str, list[dict[str, Any]]] = {
                scenario_id: [] for scenario_id in scenario_ids
            }
            for component in components:
                components_by_scenario[component.scenario_id].append(
                    {
                        "code": component.code,
                        "label_fa": component.label_fa,
                        "amount": component.amount,
                        "currency": component.currency,
                        "evidence_class": component.evidence_class,
                        "formula": component.formula,
                    }
                )

            sensitivity = analyze_scenario_sensitivity(
                tuple(
                    ScenarioCostPoint(
                        name=scenario.name,
                        quantity=scenario.quantity,
                        target_currency=scenario.target_currency,
                        per_unit_amount=scenario.per_unit_amount,
                    )
                    for scenario in scenarios
                )
            )
            return {
                "research_run_id": run_id,
                "scenarios": [
                    {
                        "name": scenario.name,
                        "quantity": scenario.quantity,
                        "target_currency": scenario.target_currency,
                        "total_amount": scenario.total_amount,
                        "per_unit_amount": scenario.per_unit_amount,
                        "components": components_by_scenario[scenario.id],
                    }
                    for scenario in scenarios
                ],
                "scenario_sensitivity": asdict(sensitivity),
            }

    def get_trade_cost_coverage(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            scenarios = tuple(
                session.scalars(
                    select(LandedCostScenarioRecord).where(
                        LandedCostScenarioRecord.research_run_id == run_id
                    )
                )
            )
            scenario_ids = [scenario.id for scenario in scenarios]
            components = (
                tuple(
                    session.scalars(
                        select(LandedCostComponentRecord).where(
                            LandedCostComponentRecord.scenario_id.in_(scenario_ids)
                        )
                    )
                )
                if scenario_ids
                else ()
            )
            components_by_scenario: dict[str, list[CostCoveragePoint]] = {
                scenario.id: [] for scenario in scenarios
            }
            for component in components:
                components_by_scenario[component.scenario_id].append(
                    CostCoveragePoint(
                        code=component.code,
                        evidence_class=component.evidence_class,
                        is_zero=component.amount == 0,
                    )
                )
            return asdict(
                analyze_trade_cost_coverage(
                    tuple(
                        ScenarioCostCoverageInput(
                            name=scenario.name,
                            components=tuple(components_by_scenario[scenario.id]),
                        )
                        for scenario in scenarios
                    )
                )
            )

    def get_research_fx_rates(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = list(
                session.execute(
                    select(
                        FXRateRecord,
                        LandedCostScenarioRecord,
                        EvidenceRecord,
                        SourceRecord,
                    )
                    .join(
                        LandedCostScenarioRecord,
                        LandedCostScenarioRecord.id == FXRateRecord.scenario_id,
                    )
                    .join(EvidenceRecord, EvidenceRecord.id == FXRateRecord.evidence_id)
                    .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                    .where(
                        FXRateRecord.research_run_id == run_id,
                        LandedCostScenarioRecord.research_run_id == run_id,
                        EvidenceRecord.research_run_id == run_id,
                    )
                ).all()
            )
            scenario_order = {"OPTIMISTIC": 0, "BASE": 1, "CONSERVATIVE": 2}
            rows.sort(
                key=lambda row: (
                    scenario_order.get(row[1].name, 99),
                    row[0].base_currency,
                    row[0].quote_currency,
                    row[0].rate_type,
                    row[0].id,
                )
            )
            return [
                {
                    "scenario_name": scenario.name,
                    "base_currency": rate.base_currency,
                    "quote_currency": rate.quote_currency,
                    "rate": rate.rate,
                    "rate_type": rate.rate_type,
                    "effective_at": rate.effective_at,
                    "source_name": source.name,
                    "source_url": evidence.source_url,
                    "retrieved_at": evidence.retrieved_at,
                    "evidence_classification": evidence.classification,
                    "evidence_confidence": evidence.confidence,
                    "transformation": evidence.transformation,
                }
                for rate, scenario, evidence, source in rows
            ]

    def get_research_assumptions(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            notes = list(
                session.scalars(
                    select(ResearchNoteRecord)
                    .where(ResearchNoteRecord.research_run_id == run_id)
                    .order_by(
                        ResearchNoteRecord.kind,
                        ResearchNoteRecord.text,
                        ResearchNoteRecord.id,
                    )
                )
            )
            return {
                "research_run_id": run_id,
                "assumptions": [note.text for note in notes if note.kind == "ASSUMPTION"],
                "unknowns": [note.text for note in notes if note.kind == "UNKNOWN"],
            }

    def get_research_evidence(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            evidence_rows = list(
                session.execute(
                    select(EvidenceRecord, SourceRecord)
                    .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                    .where(EvidenceRecord.research_run_id == run_id)
                    .order_by(EvidenceRecord.retrieved_at, EvidenceRecord.id)
                ).all()
            )
            usages: dict[str, list[dict[str, str]]] = {
                evidence.id: [] for evidence, _source in evidence_rows
            }
            observations = session.execute(
                select(
                    PriceObservationRecord.evidence_id,
                    PriceObservationRecord.external_observation_id,
                )
                .where(PriceObservationRecord.research_run_id == run_id)
                .order_by(PriceObservationRecord.external_observation_id)
            ).all()
            for evidence_id, observation_id in observations:
                usages[evidence_id].append(
                    {"kind": "PRICE_OBSERVATION", "subject_id": observation_id}
                )

            identity_claims = session.execute(
                select(
                    SupplierIdentityClaimRecord.evidence_id,
                    SupplierIdentityClaimRecord.external_claim_id,
                )
                .where(SupplierIdentityClaimRecord.research_run_id == run_id)
                .order_by(SupplierIdentityClaimRecord.external_claim_id)
            ).all()
            for evidence_id, claim_id in identity_claims:
                usages[evidence_id].append(
                    {"kind": "SUPPLIER_IDENTITY_CLAIM", "subject_id": claim_id}
                )

            rate_rows = session.execute(
                select(FXRateRecord, LandedCostScenarioRecord)
                .join(
                    LandedCostScenarioRecord,
                    LandedCostScenarioRecord.id == FXRateRecord.scenario_id,
                )
                .where(
                    FXRateRecord.research_run_id == run_id,
                    LandedCostScenarioRecord.research_run_id == run_id,
                )
            ).all()
            for rate, scenario in rate_rows:
                effective_at = rate.effective_at.isoformat() if rate.effective_at else "unspecified"
                usages[rate.evidence_id].append(
                    {
                        "kind": "FX_RATE",
                        "subject_id": (
                            f"{scenario.name}:{rate.base_currency}/{rate.quote_currency}:"
                            f"{rate.rate_type}:{effective_at}"
                        ),
                    }
                )
            for items in usages.values():
                items.sort(key=lambda item: (item["kind"], item["subject_id"]))

            return [
                {
                    "id": evidence.id,
                    "classification": evidence.classification,
                    "source_name": source.name,
                    "source_url": evidence.source_url,
                    "retrieved_at": evidence.retrieved_at,
                    "confidence": evidence.confidence,
                    "transformation": evidence.transformation,
                    "fingerprint_sha256": evidence.fingerprint,
                    "usages": usages[evidence.id],
                }
                for evidence, source in evidence_rows
            ]

    def get_evidence_freshness(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            validation = session.scalar(
                select(ResearchValidationRecord).where(
                    ResearchValidationRecord.research_run_id == run_id
                )
            )
            if validation is None:
                raise KeyError("research validation not found")
            evidence_rows = tuple(
                session.execute(
                    select(EvidenceRecord, SourceRecord)
                    .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                    .where(EvidenceRecord.research_run_id == run_id)
                )
            )
            usage_counts = {
                evidence.id: 0 for evidence, _source in evidence_rows
            }
            observation_evidence_ids = session.scalars(
                select(PriceObservationRecord.evidence_id).where(
                    PriceObservationRecord.research_run_id == run_id
                )
            )
            for evidence_id in observation_evidence_ids:
                usage_counts[evidence_id] += 1
            identity_evidence_ids = session.scalars(
                select(SupplierIdentityClaimRecord.evidence_id).where(
                    SupplierIdentityClaimRecord.research_run_id == run_id
                )
            )
            for evidence_id in identity_evidence_ids:
                usage_counts[evidence_id] += 1
            rate_evidence_ids = session.scalars(
                select(FXRateRecord.evidence_id).where(
                    FXRateRecord.research_run_id == run_id
                )
            )
            for evidence_id in rate_evidence_ids:
                usage_counts[evidence_id] += 1
            points = tuple(
                EvidenceFreshnessPoint(
                    evidence_id=evidence.id,
                    fingerprint_sha256=evidence.fingerprint,
                    classification=evidence.classification,
                    confidence=evidence.confidence,
                    source_name=source.name,
                    source_url=evidence.source_url,
                    retrieved_at=_database_utc(evidence.retrieved_at),
                    usage_count=usage_counts[evidence.id],
                )
                for evidence, source in evidence_rows
            )
            return asdict(
                analyze_evidence_freshness(
                    points,
                    evaluated_at=_database_utc(validation.evaluated_at),
                    validation_policy_version=validation.policy_version,
                )
            )

    def get_price_observations(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(
                    PriceObservationRecord,
                    ProductMatchRecord,
                    SupplierOfferRankingRecord,
                    EvidenceRecord,
                    SourceRecord,
                )
                .join(
                    ProductMatchRecord,
                    ProductMatchRecord.price_observation_id == PriceObservationRecord.id,
                )
                .join(
                    SupplierOfferRankingRecord,
                    SupplierOfferRankingRecord.price_observation_id
                    == PriceObservationRecord.id,
                )
                .join(EvidenceRecord, EvidenceRecord.id == PriceObservationRecord.evidence_id)
                .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                .where(
                    PriceObservationRecord.research_run_id == run_id,
                    ProductMatchRecord.research_run_id == run_id,
                    SupplierOfferRankingRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
                .order_by(PriceObservationRecord.external_observation_id)
            ).all()
            return [
                {
                    "external_observation_id": observation.external_observation_id,
                    "product_name": observation.product_name,
                    "product_variant": observation.product_variant,
                    "product_attributes": observation.product_attributes,
                    "supplier_name": observation.supplier_name,
                    "original_amount": observation.original_amount,
                    "original_currency": observation.original_currency,
                    "quoted_quantity": observation.quantity,
                    "unit": observation.unit,
                    "minimum_order_quantity": observation.minimum_order_quantity,
                    "incoterm": observation.incoterm,
                    "incoterm_named_place": observation.incoterm_named_place,
                    "incoterm_version": observation.incoterm_version,
                    "payment_terms": observation.payment_terms,
                    "payment_method": observation.payment_method,
                    "quote_valid_until": observation.quote_valid_until,
                    "lead_time_days": observation.lead_time_days,
                    "market_layer": observation.market_layer,
                    "normalized_amount": ranking.normalized_amount,
                    "normalized_currency": ranking.normalized_currency,
                    "comparison_group": ranking.comparison_group,
                    "product_match_classification": match.classification,
                    "product_match_score": match.score,
                    "source_name": source.name,
                    "source_url": evidence.source_url,
                    "retrieved_at": evidence.retrieved_at,
                    "evidence_classification": evidence.classification,
                    "evidence_confidence": evidence.confidence,
                    "transformation": evidence.transformation,
                }
                for observation, match, ranking, evidence, source in rows
            ]

    def get_quantity_analysis(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            run = self._require_research_run(session, run_id, tenant_id)
            opportunity = session.scalar(
                select(OpportunityRecord).where(
                    OpportunityRecord.id == run.opportunity_id,
                    OpportunityRecord.tenant_id == tenant_id,
                )
            )
            if opportunity is None:
                raise KeyError("opportunity not found")
            rows = session.execute(
                select(
                    PriceObservationRecord,
                    SupplierOfferRankingRecord,
                    EvidenceRecord,
                    SourceRecord,
                )
                .join(
                    SupplierOfferRankingRecord,
                    SupplierOfferRankingRecord.price_observation_id
                    == PriceObservationRecord.id,
                )
                .join(EvidenceRecord, EvidenceRecord.id == PriceObservationRecord.evidence_id)
                .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                .where(
                    PriceObservationRecord.research_run_id == run_id,
                    SupplierOfferRankingRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
            ).all()
            points = tuple(
                QuantityPricePoint(
                    observation_id=observation.external_observation_id,
                    supplier_name=observation.supplier_name,
                    product_name=observation.product_name,
                    product_variant=observation.product_variant,
                    product_group_key=quantity_product_key(
                        observation.product_name,
                        observation.product_variant,
                        observation.product_attributes,
                    ),
                    comparison_group=ranking.comparison_group,
                    quoted_quantity=observation.quantity,
                    minimum_order_quantity=observation.minimum_order_quantity,
                    eligible_for_requested_quantity=ranking.eligible_for_quantity,
                    original_amount=observation.original_amount,
                    original_currency=observation.original_currency,
                    normalized_amount=ranking.normalized_amount,
                    normalized_currency=ranking.normalized_currency,
                    source_name=source.name,
                    source_url=evidence.source_url,
                )
                for observation, ranking, evidence, source in rows
            )
            return asdict(analyze_quantity_points(opportunity.quantity, points))

    def get_price_distribution(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(
                    PriceObservationRecord,
                    SupplierOfferRankingRecord,
                    EvidenceRecord,
                )
                .join(
                    SupplierOfferRankingRecord,
                    SupplierOfferRankingRecord.price_observation_id
                    == PriceObservationRecord.id,
                )
                .join(EvidenceRecord, EvidenceRecord.id == PriceObservationRecord.evidence_id)
                .where(
                    PriceObservationRecord.research_run_id == run_id,
                    SupplierOfferRankingRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
            ).all()
            points = tuple(
                DistributionPricePoint(
                    observation_id=observation.external_observation_id,
                    product_name=observation.product_name,
                    product_variant=observation.product_variant,
                    product_group_key=quantity_product_key(
                        observation.product_name,
                        observation.product_variant,
                        observation.product_attributes,
                    ),
                    market_layer=observation.market_layer,
                    comparison_group=ranking.comparison_group,
                    quoted_quantity=observation.quantity,
                    normalized_amount=ranking.normalized_amount,
                    normalized_currency=ranking.normalized_currency,
                    source_url=evidence.source_url,
                )
                for observation, ranking, evidence in rows
            )
            return asdict(analyze_price_distribution(points))

    def get_incoterm_coverage(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(PriceObservationRecord, EvidenceRecord)
                .join(EvidenceRecord, EvidenceRecord.id == PriceObservationRecord.evidence_id)
                .where(
                    PriceObservationRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
            ).all()
            points = tuple(
                IncotermEvidencePoint(
                    observation_id=observation.external_observation_id,
                    incoterm=observation.incoterm,
                    incoterm_named_place=observation.incoterm_named_place,
                    incoterm_version=observation.incoterm_version,
                    supplier_name=observation.supplier_name,
                    source_url=evidence.source_url,
                )
                for observation, evidence in rows
            )
            return asdict(summarize_incoterm_coverage(points))

    def get_offer_terms_coverage(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(PriceObservationRecord, SupplierOfferRankingRecord)
                .join(
                    SupplierOfferRankingRecord,
                    SupplierOfferRankingRecord.price_observation_id
                    == PriceObservationRecord.id,
                )
                .where(
                    PriceObservationRecord.research_run_id == run_id,
                    SupplierOfferRankingRecord.research_run_id == run_id,
                )
            ).all()
            points = tuple(
                OfferTermsPoint(
                    observation_id=observation.external_observation_id,
                    supplier_name=observation.supplier_name,
                    minimum_order_quantity=observation.minimum_order_quantity,
                    product_variant=observation.product_variant,
                    product_attributes=observation.product_attributes,
                    incoterm=observation.incoterm,
                    incoterm_named_place=observation.incoterm_named_place,
                    incoterm_version=observation.incoterm_version,
                    payment_terms=observation.payment_terms,
                    payment_method=observation.payment_method,
                    quote_valid_until=observation.quote_valid_until,
                    lead_time_days=observation.lead_time_days,
                    rankable=ranking.rankable,
                    ranking_unknown_factors=tuple(ranking.unknown_factors),
                )
                for observation, ranking in rows
            )
            return asdict(summarize_offer_terms_coverage(points))

    def get_product_matches(
        self, run_id: str, *, tenant_id: str
    ) -> list[ProductMatchRecord]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            records = list(
                session.scalars(
                    select(ProductMatchRecord)
                    .where(ProductMatchRecord.research_run_id == run_id)
                    .order_by(ProductMatchRecord.score.desc(), ProductMatchRecord.id)
                )
            )
            for record in records:
                session.expunge(record)
            return records

    def get_supplier_offer_rankings(
        self, run_id: str, *, tenant_id: str
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(
                    SupplierOfferRankingRecord,
                    PriceObservationRecord,
                    EvidenceRecord,
                    SourceRecord,
                )
                .join(
                    PriceObservationRecord,
                    PriceObservationRecord.id
                    == SupplierOfferRankingRecord.price_observation_id,
                )
                .join(
                    EvidenceRecord,
                    EvidenceRecord.id == PriceObservationRecord.evidence_id,
                )
                .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                .where(SupplierOfferRankingRecord.research_run_id == run_id)
                .order_by(
                    SupplierOfferRankingRecord.comparison_group,
                    SupplierOfferRankingRecord.rank.asc().nulls_last(),
                    SupplierOfferRankingRecord.id,
                )
            ).all()
            return [
                self._supplier_offer_view(ranking, observation, evidence, source)
                for ranking, observation, evidence, source in rows
            ]

    def get_supplier_coverage(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(
                    PriceObservationRecord,
                    SupplierOfferRankingRecord,
                    EvidenceRecord,
                )
                .join(
                    SupplierOfferRankingRecord,
                    SupplierOfferRankingRecord.price_observation_id
                    == PriceObservationRecord.id,
                )
                .join(EvidenceRecord, EvidenceRecord.id == PriceObservationRecord.evidence_id)
                .where(
                    PriceObservationRecord.research_run_id == run_id,
                    SupplierOfferRankingRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
            ).all()
            points = tuple(
                SupplierEvidencePoint(
                    observation_id=observation.external_observation_id,
                    supplier_name=observation.supplier_name,
                    source_url=evidence.source_url,
                    minimum_order_quantity=observation.minimum_order_quantity,
                    incoterm=observation.incoterm,
                    rankable=ranking.rankable,
                    unknown_factors=tuple(ranking.unknown_factors),
                )
                for observation, ranking, evidence in rows
            )
            return asdict(summarize_supplier_coverage(points))

    def get_supplier_identity_claims(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            rows = session.execute(
                select(
                    SupplierIdentityClaimRecord,
                    PriceObservationRecord,
                    EvidenceRecord,
                    SourceRecord,
                )
                .join(
                    PriceObservationRecord,
                    PriceObservationRecord.id
                    == SupplierIdentityClaimRecord.price_observation_id,
                )
                .join(
                    EvidenceRecord,
                    EvidenceRecord.id == SupplierIdentityClaimRecord.evidence_id,
                )
                .join(SourceRecord, SourceRecord.id == EvidenceRecord.source_id)
                .where(
                    SupplierIdentityClaimRecord.research_run_id == run_id,
                    PriceObservationRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
            ).all()
            points = tuple(
                SupplierIdentityClaimPoint(
                    claim_id=claim.external_claim_id,
                    observation_id=observation.external_observation_id,
                    quoted_supplier_name=observation.supplier_name,
                    claimed_legal_name=claim.claimed_legal_name,
                    jurisdiction=claim.jurisdiction,
                    registration_number=claim.registration_number,
                    source_name=source.name,
                    source_url=evidence.source_url,
                    retrieved_at=_database_utc(evidence.retrieved_at),
                    evidence_classification=evidence.classification,
                    evidence_confidence=evidence.confidence,
                    transformation=evidence.transformation,
                )
                for claim, observation, evidence, source in rows
            )
            summary = summarize_supplier_identity_claims(points)
            return {"research_run_id": run_id, **asdict(summary)}

    def get_executive_summary(
        self,
        run_id: str,
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            validation = session.scalar(
                select(ResearchValidationRecord).where(
                    ResearchValidationRecord.research_run_id == run_id
                )
            )
            base_scenario = session.scalar(
                select(LandedCostScenarioRecord).where(
                    LandedCostScenarioRecord.research_run_id == run_id,
                    LandedCostScenarioRecord.name == "BASE",
                )
            )
            if validation is None or base_scenario is None:
                raise KeyError("research executive summary not found")

            issues = tuple(
                session.scalars(
                    select(ValidationIssueRecord).where(
                        ValidationIssueRecord.research_run_id == run_id
                    )
                )
            )
            unknowns = tuple(
                session.scalars(
                    select(ResearchNoteRecord.text).where(
                        ResearchNoteRecord.research_run_id == run_id,
                        ResearchNoteRecord.kind == "UNKNOWN",
                    )
                )
            )
            gap_summary = summarize_data_gaps(
                tuple(
                    DataGapIssue(
                        code=issue.code,
                        severity=issue.severity,
                        message_fa=issue.message_fa,
                        subject_type=issue.subject_type,
                        subject_id=issue.subject_id,
                        details=issue.details,
                    )
                    for issue in issues
                ),
                unknowns,
            )

            candidate_rows = session.execute(
                select(
                    SupplierOfferRankingRecord,
                    PriceObservationRecord,
                    EvidenceRecord,
                )
                .join(
                    PriceObservationRecord,
                    PriceObservationRecord.id
                    == SupplierOfferRankingRecord.price_observation_id,
                )
                .join(EvidenceRecord, EvidenceRecord.id == PriceObservationRecord.evidence_id)
                .where(
                    SupplierOfferRankingRecord.research_run_id == run_id,
                    SupplierOfferRankingRecord.rank == 1,
                    PriceObservationRecord.research_run_id == run_id,
                    EvidenceRecord.research_run_id == run_id,
                )
            ).all()
            candidates: list[ExecutiveSupplierCandidate] = []
            for ranking, observation, evidence in candidate_rows:
                candidates.append(
                    self._executive_supplier_candidate(ranking, observation, evidence)
                )
            return asdict(
                build_executive_summary(
                    validation_disposition=validation.disposition,
                    confidence_score=validation.confidence_score,
                    confidence_label=validation.confidence_label,
                    base_landed_cost_per_unit=base_scenario.per_unit_amount,
                    base_landed_cost_currency=base_scenario.target_currency,
                    leading_supplier_candidates=tuple(candidates),
                    data_gap_status=gap_summary.status,
                    data_gap_issue_count=gap_summary.issue_count,
                    declared_unknown_count=gap_summary.declared_unknown_count,
                )
            )

    @staticmethod
    def _executive_supplier_candidate(
        ranking: SupplierOfferRankingRecord,
        observation: PriceObservationRecord,
        evidence: EvidenceRecord,
    ) -> ExecutiveSupplierCandidate:
        if (
            observation.supplier_name is None
            or ranking.normalized_amount is None
            or ranking.normalized_currency is None
        ):
            raise KeyError("ranked supplier candidate is incomplete")
        return ExecutiveSupplierCandidate(
            observation_id=observation.external_observation_id,
            supplier_name=observation.supplier_name,
            original_amount=observation.original_amount,
            original_currency=observation.original_currency,
            normalized_amount=ranking.normalized_amount,
            normalized_currency=ranking.normalized_currency,
            total_score=ranking.total_score,
            source_url=evidence.source_url,
            evidence_classification=evidence.classification,
            evidence_confidence=evidence.confidence,
        )

    @staticmethod
    def _supplier_offer_view(
        ranking: SupplierOfferRankingRecord,
        observation: PriceObservationRecord,
        evidence: EvidenceRecord,
        source: SourceRecord,
    ) -> dict[str, Any]:
        return {
            "external_observation_id": ranking.external_observation_id,
            "supplier_name": ranking.supplier_name,
            "comparison_group": ranking.comparison_group,
            "rank": ranking.rank,
            "eligible_for_quantity": ranking.eligible_for_quantity,
            "rankable": ranking.rankable,
            "normalized_amount": ranking.normalized_amount,
            "normalized_currency": ranking.normalized_currency,
            "total_score": ranking.total_score,
            "component_scores": ranking.component_scores,
            "unknown_factors": ranking.unknown_factors,
            "explanation_fa": ranking.explanation_fa,
            "policy_version": ranking.policy_version,
            "product_name": observation.product_name,
            "original_amount": observation.original_amount,
            "original_currency": observation.original_currency,
            "quoted_quantity": observation.quantity,
            "unit": observation.unit,
            "minimum_order_quantity": observation.minimum_order_quantity,
            "incoterm": observation.incoterm,
            "incoterm_named_place": observation.incoterm_named_place,
            "incoterm_version": observation.incoterm_version,
            "payment_terms": observation.payment_terms,
            "payment_method": observation.payment_method,
            "quote_valid_until": observation.quote_valid_until,
            "lead_time_days": observation.lead_time_days,
            "source_name": source.name,
            "source_url": evidence.source_url,
            "retrieved_at": evidence.retrieved_at,
            "evidence_classification": evidence.classification,
            "evidence_confidence": evidence.confidence,
            "transformation": evidence.transformation,
        }

    def _load_idempotent_completion(
        self,
        *,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        tenant_id: str,
    ) -> ResearchCompletion | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                    IdempotencyRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                return None
            return self._completion_from_idempotency(record, request_hash)

    @staticmethod
    def _require_research_run(
        session: Session,
        run_id: str,
        tenant_id: str,
    ) -> ResearchRunRecord:
        run = session.scalar(
            select(ResearchRunRecord).where(
                ResearchRunRecord.id == run_id,
                ResearchRunRecord.tenant_id == tenant_id,
            )
        )
        if run is None:
            raise KeyError("research run not found")
        return run

    @staticmethod
    def _completion_from_idempotency(
        record: IdempotencyRecord,
        request_hash: str,
    ) -> ResearchCompletion:
        if record.request_hash != request_hash:
            raise IdempotencyConflictError(
                "idempotency key was already used with a different request payload"
            )
        completion = ResearchCompletion(**record.response_payload)
        return replace(completion, idempotency_replayed=True)

    @classmethod
    def _evidence(
        cls,
        session: Session,
        run_id: str,
        evidence: Evidence,
        cache: dict[str, EvidenceRecord],
    ) -> EvidenceRecord:
        fingerprint = evidence_fingerprint_sha256(evidence)
        cached = cache.get(fingerprint)
        if cached is not None:
            return cached
        source = session.scalar(
            select(SourceRecord).where(SourceRecord.name == evidence.source_name)
        )
        if source is None:
            source = SourceRecord(
                id=str(uuid4()), name=evidence.source_name, created_at=datetime.now(UTC)
            )
            session.add(source)
            session.flush()
        record = EvidenceRecord(
            id=str(uuid4()),
            research_run_id=run_id,
            source_id=source.id,
            classification=evidence.classification.value,
            source_url=evidence.source_url,
            retrieved_at=evidence.retrieved_at,
            raw_value=evidence.raw_value,
            confidence=evidence.confidence.value,
            transformation=evidence.transformation,
            fingerprint=fingerprint,
        )
        session.add(record)
        cache[fingerprint] = record
        return record

    @staticmethod
    def _audit(
        session: Session,
        correlation_id: str,
        tenant_id: str,
        actor_id: str,
        aggregate_type: str,
        aggregate_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            AuditEventRecord(
                id=str(uuid4()),
                tenant_id=tenant_id,
                actor_id=actor_id,
                correlation_id=correlation_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                action=action,
                payload=payload,
                occurred_at=datetime.now(UTC),
            )
        )
