from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from trade_agent.application.matching import normalize_product_text
from trade_agent.application.pagination import PageCursor, encode_cursor
from trade_agent.application.ports import ResearchCompletion
from trade_agent.application.research import ResearchResult
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
    SupplierOfferRankingRecord,
    ValidationIssueRecord,
)


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

            fx_keys: set[tuple[str, str, str, datetime | None]] = set()
            for scenario_input in result.case.scenarios:
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
                            evidence_id=evidence.id,
                            base_currency=rate.base_currency,
                            quote_currency=rate.quote_currency,
                            rate=rate.rate,
                            rate_type=rate.rate_type,
                            effective_at=rate.effective_at,
                        )
                    )

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
                    "fx_rate_count": len(fx_keys),
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
                fx_rate_count=len(fx_keys),
                scenario_count=len(result.scenarios),
                validation_disposition=validation.disposition.value,
                validation_issue_count=len(validation.issues),
                confidence_score=validation.confidence_score,
                confidence_label=validation.confidence_label.value,
                report_sha256=report_hash,
                idempotency_replayed=False,
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
            leading_offers = list(
                session.scalars(
                    select(SupplierOfferRankingRecord)
                    .where(
                        SupplierOfferRankingRecord.research_run_id == run.id,
                        SupplierOfferRankingRecord.rank == 1,
                    )
                    .order_by(
                        SupplierOfferRankingRecord.comparison_group,
                        SupplierOfferRankingRecord.id,
                    )
                )
            )
            if report is None or validation is None or not scenarios:
                raise KeyError("opportunity decision not found")

            scenario_order = {"OPTIMISTIC": 0, "BASE": 1, "CONSERVATIVE": 2}
            scenarios.sort(key=lambda item: (scenario_order.get(item.name, 99), item.id))
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
            for record in (run, report, *scenarios, *leading_offers):
                session.expunge(record)
            return {
                "opportunity_id": opportunity_id,
                "research_run": run,
                "validation": validation_view,
                "scenarios": scenarios,
                "leading_offers": leading_offers,
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
    ) -> list[SupplierOfferRankingRecord]:
        with self._session_factory() as session:
            self._require_research_run(session, run_id, tenant_id)
            records = list(
                session.scalars(
                    select(SupplierOfferRankingRecord)
                    .where(SupplierOfferRankingRecord.research_run_id == run_id)
                    .order_by(
                        SupplierOfferRankingRecord.comparison_group,
                        SupplierOfferRankingRecord.rank.asc().nulls_last(),
                        SupplierOfferRankingRecord.id,
                    )
                )
            )
            for record in records:
                session.expunge(record)
            return records

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

    @staticmethod
    def _evidence_fingerprint(evidence: Evidence) -> str:
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

    @classmethod
    def _evidence(
        cls,
        session: Session,
        run_id: str,
        evidence: Evidence,
        cache: dict[str, EvidenceRecord],
    ) -> EvidenceRecord:
        fingerprint = cls._evidence_fingerprint(evidence)
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
