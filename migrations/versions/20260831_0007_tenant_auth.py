"""Add tenant and actor boundaries to mutable aggregates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0007"
down_revision: str | None = "20260831_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="legacy"),
    )
    op.create_index(
        "ix_opportunities_tenant_status_created",
        "opportunities",
        ["tenant_id", "status", "created_at"],
    )
    op.add_column(
        "research_runs",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="legacy"),
    )
    op.create_index(
        "ix_research_runs_tenant_created_at",
        "research_runs",
        ["tenant_id", "created_at"],
    )
    op.add_column(
        "audit_events",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_id", sa.String(100), nullable=False, server_default="legacy"),
    )
    op.create_index(
        "ix_audit_tenant_time",
        "audit_events",
        ["tenant_id", "occurred_at"],
    )
    op.add_column(
        "idempotency_records",
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="legacy"),
    )
    op.create_index(
        "ix_idempotency_tenant_created",
        "idempotency_records",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_tenant_created", table_name="idempotency_records")
    op.drop_column("idempotency_records", "tenant_id")
    op.drop_index("ix_audit_tenant_time", table_name="audit_events")
    op.drop_column("audit_events", "actor_id")
    op.drop_column("audit_events", "tenant_id")
    op.drop_index("ix_research_runs_tenant_created_at", table_name="research_runs")
    op.drop_column("research_runs", "tenant_id")
    op.drop_index(
        "ix_opportunities_tenant_status_created",
        table_name="opportunities",
    )
    op.drop_column("opportunities", "tenant_id")
