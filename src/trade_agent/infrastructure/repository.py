from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from trade_agent.domain.workflow import (
    OpportunityStatus,
    ResearchRunStatus,
    VersionConflictError,
    ensure_research_transition,
)
from trade_agent.infrastructure.database import (
    AuditEventRecord,
    OpportunityRecord,
    ResearchRunRecord,
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
