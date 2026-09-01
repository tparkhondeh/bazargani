"""Add explicit research recalculation lineage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0015"
down_revision: str | None = "20260901_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("supersedes_research_run_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "research_runs",
        sa.Column("recalculation_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_research_runs_supersedes",
        "research_runs",
        "research_runs",
        ["supersedes_research_run_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_research_runs_recalculation_lineage",
        "research_runs",
        "(supersedes_research_run_id IS NULL AND recalculation_reason IS NULL) OR "
        "(supersedes_research_run_id IS NOT NULL AND recalculation_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_research_runs_not_self_superseding",
        "research_runs",
        "supersedes_research_run_id IS NULL OR supersedes_research_run_id <> id",
    )
    op.create_index(
        "ix_research_runs_supersedes",
        "research_runs",
        ["supersedes_research_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_runs_supersedes", table_name="research_runs")
    op.drop_constraint(
        "ck_research_runs_not_self_superseding",
        "research_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_research_runs_recalculation_lineage",
        "research_runs",
        type_="check",
    )
    op.drop_constraint(
        "fk_research_runs_supersedes",
        "research_runs",
        type_="foreignkey",
    )
    op.drop_column("research_runs", "recalculation_reason")
    op.drop_column("research_runs", "supersedes_research_run_id")
