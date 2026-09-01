"""Persist deterministic product matching outcomes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0004"
down_revision: str | None = "20260831_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_observations",
        sa.Column(
            "product_attributes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "product_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("price_observation_id", sa.String(36), nullable=False),
        sa.Column("external_observation_id", sa.String(200), nullable=False),
        sa.Column("classification", sa.String(30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("name_similarity", sa.Numeric(8, 6), nullable=False),
        sa.Column("requested_attributes", sa.JSON(), nullable=False),
        sa.Column("observed_attributes", sa.JSON(), nullable=False),
        sa.Column("matched_attributes", sa.JSON(), nullable=False),
        sa.Column("conflicting_attributes", sa.JSON(), nullable=False),
        sa.Column("missing_attributes", sa.JSON(), nullable=False),
        sa.Column("explanation_fa", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["price_observation_id"], ["price_observations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "price_observation_id", name="uq_product_match_price_observation"
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_product_matches_score_range"),
        sa.CheckConstraint(
            "name_similarity >= 0 AND name_similarity <= 1",
            name="ck_product_matches_name_similarity_range",
        ),
    )
    op.create_index(
        "ix_product_matches_run_class",
        "product_matches",
        ["research_run_id", "classification"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_matches_run_class", table_name="product_matches")
    op.drop_table("product_matches")
    op.drop_column("price_observations", "product_attributes")
