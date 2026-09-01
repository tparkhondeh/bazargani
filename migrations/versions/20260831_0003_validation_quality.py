"""Persist validation summaries, issues, and explicit price units."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0003"
down_revision: str | None = "20260831_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_observations",
        sa.Column(
            "unit",
            sa.String(50),
            nullable=False,
            server_default="UNSPECIFIED",
        ),
    )
    op.create_table(
        "research_validations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False, unique=True),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("confidence_label", sa.String(20), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 100",
            name="ck_research_validations_confidence_range",
        ),
    )
    op.create_table(
        "validation_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message_fa", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.String(50), nullable=False),
        sa.Column("subject_id", sa.String(200), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_validation_issues_run_severity",
        "validation_issues",
        ["research_run_id", "severity"],
    )


def downgrade() -> None:
    op.drop_index("ix_validation_issues_run_severity", table_name="validation_issues")
    op.drop_table("validation_issues")
    op.drop_table("research_validations")
    op.drop_column("price_observations", "unit")
