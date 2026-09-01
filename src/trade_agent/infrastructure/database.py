from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class OpportunityRecord(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_opportunities_quantity_positive"),
        CheckConstraint("version > 0", name="ck_opportunities_version_positive"),
        Index("ix_opportunities_status_created_at", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[int] = mapped_column(Integer)
    target_market: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    runs: Mapped[list[ResearchRunRecord]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class ResearchRunRecord(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_research_runs_version_positive"),
        Index("ix_research_runs_opportunity_created_at", "opportunity_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    opportunity: Mapped[OpportunityRecord] = relationship(back_populates="runs")


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_aggregate_time", "aggregate_type", "aggregate_id", "occurred_at"),
        Index("ix_audit_correlation_id", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceRecord(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvidenceRecord(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("research_run_id", "fingerprint", name="uq_evidence_run_fingerprint"),
        Index("ix_evidence_run_retrieved", "research_run_id", "retrieved_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id"))
    classification: Mapped[str] = mapped_column(String(30))
    source_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20))
    transformation: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class PriceObservationRecord(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint(
            "research_run_id", "external_observation_id", name="uq_price_run_observation"
        ),
        CheckConstraint("quantity > 0", name="ck_price_observations_quantity_positive"),
        CheckConstraint(
            "minimum_order_quantity IS NULL OR minimum_order_quantity > 0",
            name="ck_price_observations_moq_positive",
        ),
        Index("ix_price_observations_run_product", "research_run_id", "product_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence.id"))
    external_observation_id: Mapped[str] = mapped_column(String(200))
    product_name: Mapped[str] = mapped_column(String(300))
    supplier_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    original_currency: Mapped[str] = mapped_column(String(3))
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(50))
    minimum_order_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    incoterm: Mapped[str | None] = mapped_column(String(10), nullable=True)
    product_variant: Mapped[str | None] = mapped_column(String(300), nullable=True)
    product_attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    market_layer: Mapped[str] = mapped_column(String(50))


class ProductMatchRecord(Base):
    __tablename__ = "product_matches"
    __table_args__ = (
        UniqueConstraint("price_observation_id", name="uq_product_match_price_observation"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_product_matches_score_range"),
        CheckConstraint(
            "name_similarity >= 0 AND name_similarity <= 1",
            name="ck_product_matches_name_similarity_range",
        ),
        Index("ix_product_matches_run_class", "research_run_id", "classification"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    price_observation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("price_observations.id", ondelete="CASCADE")
    )
    external_observation_id: Mapped[str] = mapped_column(String(200))
    classification: Mapped[str] = mapped_column(String(30))
    score: Mapped[int] = mapped_column(Integer)
    name_similarity: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    requested_attributes: Mapped[dict[str, str]] = mapped_column(JSON)
    observed_attributes: Mapped[dict[str, str]] = mapped_column(JSON)
    matched_attributes: Mapped[list[str]] = mapped_column(JSON)
    conflicting_attributes: Mapped[list[str]] = mapped_column(JSON)
    missing_attributes: Mapped[list[str]] = mapped_column(JSON)
    explanation_fa: Mapped[list[str]] = mapped_column(JSON)
    policy_version: Mapped[str] = mapped_column(String(50))


class FXRateRecord(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint(
            "research_run_id",
            "base_currency",
            "quote_currency",
            "rate_type",
            "effective_at",
            name="uq_fx_run_pair_type_effective",
        ),
        CheckConstraint("rate > 0", name="ck_fx_rates_positive"),
        Index("ix_fx_rates_run_pair", "research_run_id", "base_currency", "quote_currency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    evidence_id: Mapped[str] = mapped_column(String(36), ForeignKey("evidence.id"))
    base_currency: Mapped[str] = mapped_column(String(3))
    quote_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    rate_type: Mapped[str] = mapped_column(String(100))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LandedCostScenarioRecord(Base):
    __tablename__ = "landed_cost_scenarios"
    __table_args__ = (
        UniqueConstraint("research_run_id", "name", name="uq_scenario_run_name"),
        CheckConstraint("quantity > 0", name="ck_scenarios_quantity_positive"),
        CheckConstraint("total_amount >= 0", name="ck_scenarios_total_nonnegative"),
        CheckConstraint("per_unit_amount >= 0", name="ck_scenarios_unit_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[int] = mapped_column(Integer)
    target_currency: Mapped[str] = mapped_column(String(3))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    per_unit_amount: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LandedCostComponentRecord(Base):
    __tablename__ = "landed_cost_components"
    __table_args__ = (
        UniqueConstraint("scenario_id", "code", name="uq_component_scenario_code"),
        CheckConstraint("amount >= 0", name="ck_components_amount_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("landed_cost_scenarios.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(100))
    label_fa: Mapped[str] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    currency: Mapped[str] = mapped_column(String(3))
    evidence_class: Mapped[str] = mapped_column(String(30))
    formula: Mapped[str] = mapped_column(Text)


class ResearchNoteRecord(Base):
    __tablename__ = "research_notes"
    __table_args__ = (Index("ix_research_notes_run_kind", "research_run_id", "kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)


class ResearchValidationRecord(Base):
    __tablename__ = "research_validations"
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="ck_research_validations_confidence_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE"), unique=True
    )
    policy_version: Mapped[str] = mapped_column(String(50))
    disposition: Mapped[str] = mapped_column(String(30))
    confidence_score: Mapped[int] = mapped_column(Integer)
    confidence_label: Mapped[str] = mapped_column(String(20))
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ValidationIssueRecord(Base):
    __tablename__ = "validation_issues"
    __table_args__ = (
        Index("ix_validation_issues_run_severity", "research_run_id", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    message_fa: Mapped[str] = mapped_column(Text)
    subject_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class DecisionReportRecord(Base):
    __tablename__ = "decision_reports"
    __table_args__ = (UniqueConstraint("research_run_id", name="uq_report_research_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    case_id: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
