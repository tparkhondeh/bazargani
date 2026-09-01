"""Add an append-only research review decision ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0008"
down_revision: str | None = "20260831_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("reviewer_actor_id", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(30), nullable=False),
        sa.Column("resulting_status", sa.String(30), nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVE', 'REJECT')",
            name="ck_research_reviews_decision",
        ),
        sa.CheckConstraint(
            "resulting_version = previous_version + 1",
            name="ck_research_reviews_version_increment",
        ),
        sa.CheckConstraint(
            "previous_version > 0",
            name="ck_research_reviews_previous_version_positive",
        ),
        sa.CheckConstraint(
            "previous_status IN "
            "('NEEDS_VERIFICATION', 'NEEDS_HUMAN_REVIEW', 'PARTIAL')",
            name="ck_research_reviews_previous_status",
        ),
        sa.CheckConstraint(
            "resulting_status IN ('COMPLETED', 'CANCELLED')",
            name="ck_research_reviews_resulting_status",
        ),
        sa.CheckConstraint(
            "(decision = 'APPROVE' AND resulting_status = 'COMPLETED') OR "
            "(decision = 'REJECT' AND resulting_status = 'CANCELLED')",
            name="ck_research_reviews_decision_status",
        ),
    )
    op.create_index(
        "ix_research_reviews_tenant_run_created",
        "research_reviews",
        ["tenant_id", "research_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_reviews_tenant_run_created",
        table_name="research_reviews",
    )
    op.drop_table("research_reviews")
