"""Add append-only supplier identity claim reviews."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0014"
down_revision: str | None = "20260901_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DECISIONS = "'EVIDENCE_SUPPORTED', 'EVIDENCE_CONTRADICTED', 'INCONCLUSIVE'"


def upgrade() -> None:
    op.create_table(
        "supplier_identity_claim_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("supplier_identity_claim_id", sa.String(36), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["supplier_identity_claim_id"],
            ["supplier_identity_claims.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"decision IN ({_DECISIONS})",
            name="ck_supplier_identity_reviews_decision",
        ),
        sa.CheckConstraint(
            f"previous_status IN ('UNREVIEWED', {_DECISIONS})",
            name="ck_supplier_identity_reviews_previous_status",
        ),
        sa.CheckConstraint(
            f"resulting_status IN ({_DECISIONS})",
            name="ck_supplier_identity_reviews_resulting_status",
        ),
        sa.CheckConstraint(
            "decision = resulting_status",
            name="ck_supplier_identity_reviews_decision_status",
        ),
        sa.CheckConstraint(
            "resulting_version = previous_version + 1",
            name="ck_supplier_identity_reviews_version_increment",
        ),
        sa.CheckConstraint(
            "previous_version >= 0",
            name="ck_supplier_identity_reviews_previous_version_nonnegative",
        ),
        sa.CheckConstraint(
            "(previous_version = 0 AND previous_status = 'UNREVIEWED') OR "
            "(previous_version > 0 AND previous_status <> 'UNREVIEWED')",
            name="ck_supplier_identity_reviews_initial_status",
        ),
        sa.UniqueConstraint(
            "supplier_identity_claim_id",
            "resulting_version",
            name="uq_supplier_identity_reviews_claim_version",
        ),
    )
    op.create_index(
        "ix_supplier_identity_reviews_tenant_run_claim_version",
        "supplier_identity_claim_reviews",
        [
            "tenant_id",
            "research_run_id",
            "supplier_identity_claim_id",
            "resulting_version",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_supplier_identity_reviews_tenant_run_claim_version",
        table_name="supplier_identity_claim_reviews",
    )
    op.drop_table("supplier_identity_claim_reviews")
