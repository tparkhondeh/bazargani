from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from trade_agent.application.ports import ResearchCompletion
from trade_agent.application.research import ResearchResult
from trade_agent.domain.models import Evidence
from trade_agent.domain.workflow import (
    InvalidTransitionError,
    OpportunityStatus,
    ResearchRunStatus,
    VersionConflictError,
    ensure_research_transition,
)
from trade_agent.infrastructure.database import (
    AuditEventRecord,
    DecisionReportRecord,
    EvidenceRecord,
    FXRateRecord,
    LandedCostComponentRecord,
    LandedCostScenarioRecord,
    OpportunityRecord,
    PriceObservationRecord,
    ResearchNoteRecord,
    ResearchRunRecord,
    SourceRecord,
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
    ) -> OpportunityRecord:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        now = datetime.now(UTC)
        record = OpportunityRecord(
            id=str(uuid4()),
            product_name=product_name.strip(),
            quantity=quantity,
            target_market=target_market.strip(),
            status=OpportunityStatus.RESEARCHING.value,
            created_at=now,
            updated_at=now,
        )
        if not record.product_name or not record.target_market:
            raise ValueError("product_name and target_market are required")
        with self._session_factory.begin() as session:
            session.add(record)
            self._audit(session, correlation_id, "Opportunity", record.id, "CREATED", {})
        return record

    def get_opportunity(self, opportunity_id: str) -> OpportunityRecord:
        with self._session_factory() as session:
            record = session.get(OpportunityRecord, opportunity_id)
            if record is None:
                raise KeyError("opportunity not found")
            session.expunge(record)
            return record

    def create_research_run(self, *, opportunity_id: str, correlation_id: str) -> ResearchRunRecord:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            if session.get(OpportunityRecord, opportunity_id) is None:
                raise KeyError("opportunity not found")
            record = ResearchRunRecord(
                id=str(uuid4()),
                opportunity_id=opportunity_id,
                status=ResearchRunStatus.CREATED.value,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            self._audit(session, correlation_id, "ResearchRun", record.id, "CREATED", {})
        return record

    def transition_research_run(
        self,
        *,
        run_id: str,
        target: ResearchRunStatus,
        expected_version: int,
        correlation_id: str,
    ) -> ResearchRunRecord:
        with self._session_factory.begin() as session:
            statement = (
                select(ResearchRunRecord).where(ResearchRunRecord.id == run_id).with_for_update()
            )
            record = session.scalar(statement)
            if record is None:
                raise KeyError("research run not found")
            if record.version != expected_version:
                raise VersionConflictError(
                    f"expected version {expected_version}, current version {record.version}"
                )
            current = ResearchRunStatus(record.status)
            ensure_research_transition(current, target)
            record.status = target.value
            record.version += 1
            record.updated_at = datetime.now(UTC)
            self._audit(
                session,
                correlation_id,
                "ResearchRun",
                record.id,
                "STATUS_CHANGED",
                {"from": current.value, "to": target.value, "version": record.version},
            )
        return record

    def persist_research_result(
        self,
        *,
        run_id: str,
        result: ResearchResult,
        report_markdown: str,
        expected_version: int,
        correlation_id: str,
    ) -> ResearchCompletion:
        with self._session_factory.begin() as session:
            statement = (
                select(ResearchRunRecord).where(ResearchRunRecord.id == run_id).with_for_update()
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

            opportunity = session.get(OpportunityRecord, run.opportunity_id)
            if opportunity is None:
                raise KeyError("opportunity not found")
            if opportunity.quantity != result.case.quantity:
                raise ValueError("bundle quantity does not match the opportunity")
            if opportunity.product_name.casefold() != result.case.product_name.casefold():
                raise ValueError("bundle product_name does not match the opportunity")

            evidence_cache: dict[str, EvidenceRecord] = {}
            for observation in result.case.observations:
                evidence = self._evidence(session, run_id, observation.evidence, evidence_cache)
                session.add(
                    PriceObservationRecord(
                        id=str(uuid4()),
                        research_run_id=run_id,
                        evidence_id=evidence.id,
                        external_observation_id=observation.observation_id,
                        product_name=observation.product_name,
                        supplier_name=observation.supplier_name,
                        original_amount=observation.unit_price.amount,
                        original_currency=observation.unit_price.currency,
                        quantity=observation.quantity,
                        minimum_order_quantity=observation.minimum_order_quantity,
                        incoterm=observation.incoterm,
                        product_variant=observation.product_variant,
                        market_layer=observation.market_layer,
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
                seen_codes: set[str] = set()
                for component in scenario_result.components:
                    if component.code in seen_codes:
                        raise ValueError(
                            "duplicate component code in "
                            f"{scenario_result.name}: {component.code}"
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
            run.status = ResearchRunStatus.COMPLETED.value
            run.version += 1
            run.updated_at = datetime.now(UTC)
            self._audit(
                session,
                correlation_id,
                "ResearchRun",
                run.id,
                "RESULTS_PERSISTED",
                {
                    "case_id": result.case.case_id,
                    "evidence_count": len(evidence_cache),
                    "price_observation_count": len(result.case.observations),
                    "fx_rate_count": len(fx_keys),
                    "scenario_count": len(result.scenarios),
                    "report_sha256": report_hash,
                    "version": run.version,
                },
            )

        return ResearchCompletion(
            research_run_id=run_id,
            status=ResearchRunStatus.COMPLETED.value,
            version=expected_version + 1,
            evidence_count=len(evidence_cache),
            price_observation_count=len(result.case.observations),
            fx_rate_count=len(fx_keys),
            scenario_count=len(result.scenarios),
            report_sha256=report_hash,
        )

    def get_research_report(self, run_id: str) -> DecisionReportRecord:
        with self._session_factory() as session:
            report = session.scalar(
                select(DecisionReportRecord).where(DecisionReportRecord.research_run_id == run_id)
            )
            if report is None:
                raise KeyError("research report not found")
            session.expunge(report)
            return report

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
        aggregate_type: str,
        aggregate_id: str,
        action: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            AuditEventRecord(
                id=str(uuid4()),
                correlation_id=correlation_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                action=action,
                payload=payload,
                occurred_at=datetime.now(UTC),
            )
        )
