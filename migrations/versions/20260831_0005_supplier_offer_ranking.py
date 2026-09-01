"""Persist explainable quantity-aware supplier offer rankings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0005"
down_revision: str | None = "20260831_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "supplier_offer_rankings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("price_observation_id", sa.String(36), nullable=False),
        sa.Column("external_observation_id", sa.String(200), nullable=False),
        sa.Column("supplier_name", sa.String(300), nullable=True),
        sa.Column("comparison_group", sa.String(100), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("eligible_for_quantity", sa.Boolean(), nullable=False),
        sa.Column("rankable", sa.Boolean(), nullable=False),
        sa.Column("normalized_amount", sa.Numeric(28, 8), nullable=True),
        sa.Column("normalized_currency", sa.String(3), nullable=True),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column("component_scores", sa.JSON(), nullable=False),
        sa.Column("unknown_factors", sa.JSON(), nullable=False),
        sa.Column("explanation_fa", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["price_observation_id"], ["price_observations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "price_observation_id", name="uq_supplier_ranking_price_observation"
        ),
        sa.CheckConstraint(
            "total_score >= 0 AND total_score <= 100",
            name="ck_supplier_rankings_score_range",
        ),
        sa.CheckConstraint(
            "rank IS NULL OR rank > 0",
            name="ck_supplier_rankings_rank_positive",
        ),
    )
    op.create_index(
        "ix_supplier_rankings_run_group",
        "supplier_offer_rankings",
        ["research_run_id", "comparison_group", "rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_rankings_run_group", table_name="supplier_offer_rankings")
    op.drop_table("supplier_offer_rankings")
