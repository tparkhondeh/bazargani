"""Persist evidence-backed research results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0002"
down_revision: str | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("classification", sa.String(30), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("transformation", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.UniqueConstraint("research_run_id", "fingerprint", name="uq_evidence_run_fingerprint"),
    )
    op.create_index("ix_evidence_run_retrieved", "evidence", ["research_run_id", "retrieved_at"])
    op.create_table(
        "price_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("external_observation_id", sa.String(200), nullable=False),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("supplier_name", sa.String(300), nullable=True),
        sa.Column("original_amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("original_currency", sa.String(3), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("minimum_order_quantity", sa.Integer(), nullable=True),
        sa.Column("incoterm", sa.String(10), nullable=True),
        sa.Column("product_variant", sa.String(300), nullable=True),
        sa.Column("market_layer", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.CheckConstraint("quantity > 0", name="ck_price_observations_quantity_positive"),
        sa.CheckConstraint(
            "minimum_order_quantity IS NULL OR minimum_order_quantity > 0",
            name="ck_price_observations_moq_positive",
        ),
        sa.UniqueConstraint(
            "research_run_id", "external_observation_id", name="uq_price_run_observation"
        ),
    )
    op.create_index(
        "ix_price_observations_run_product",
        "price_observations",
        ["research_run_id", "product_name"],
    )
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(28, 12), nullable=False),
        sa.Column("rate_type", sa.String(100), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.CheckConstraint("rate > 0", name="ck_fx_rates_positive"),
        sa.UniqueConstraint(
            "research_run_id",
            "base_currency",
            "quote_currency",
            "rate_type",
            "effective_at",
            name="uq_fx_run_pair_type_effective",
        ),
    )
    op.create_index(
        "ix_fx_rates_run_pair", "fx_rates", ["research_run_id", "base_currency", "quote_currency"]
    )
    op.create_table(
        "landed_cost_scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("target_currency", sa.String(3), nullable=False),
        sa.Column("total_amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("per_unit_amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("quantity > 0", name="ck_scenarios_quantity_positive"),
        sa.CheckConstraint("total_amount >= 0", name="ck_scenarios_total_nonnegative"),
        sa.CheckConstraint("per_unit_amount >= 0", name="ck_scenarios_unit_nonnegative"),
        sa.UniqueConstraint("research_run_id", "name", name="uq_scenario_run_name"),
    )
    op.create_table(
        "landed_cost_components",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("label_fa", sa.String(300), nullable=False),
        sa.Column("amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("evidence_class", sa.String(30), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["landed_cost_scenarios.id"], ondelete="CASCADE"),
        sa.CheckConstraint("amount >= 0", name="ck_components_amount_nonnegative"),
        sa.UniqueConstraint("scenario_id", "code", name="uq_component_scenario_code"),
    )
    op.create_table(
        "research_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_research_notes_run_kind", "research_notes", ["research_run_id", "kind"])
    op.create_table(
        "decision_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(200), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("research_run_id", name="uq_report_research_run"),
    )


def downgrade() -> None:
    op.drop_table("decision_reports")
    op.drop_table("research_notes")
    op.drop_table("landed_cost_components")
    op.drop_table("landed_cost_scenarios")
    op.drop_table("fx_rates")
    op.drop_table("price_observations")
    op.drop_table("evidence")
    op.drop_table("sources")
