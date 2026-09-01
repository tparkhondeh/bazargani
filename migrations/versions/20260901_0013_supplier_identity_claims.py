"""Add immutable evidence-bound supplier identity claims."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0013"
down_revision: str | None = "20260901_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "supplier_identity_claims",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("research_run_id", sa.String(36), nullable=False),
        sa.Column("price_observation_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("external_claim_id", sa.String(200), nullable=False),
        sa.Column("claimed_legal_name", sa.String(300), nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=False),
        sa.Column("registration_number", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["price_observation_id"],
            ["price_observations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "research_run_id",
            "external_claim_id",
            name="uq_supplier_identity_claims_run_external_id",
        ),
        sa.CheckConstraint(
            "length(trim(external_claim_id)) > 0",
            name="ck_supplier_identity_claims_external_id_required",
        ),
        sa.CheckConstraint(
            "length(trim(claimed_legal_name)) > 0",
            name="ck_supplier_identity_claims_legal_name_required",
        ),
        sa.CheckConstraint(
            "length(trim(jurisdiction)) > 0",
            name="ck_supplier_identity_claims_jurisdiction_required",
        ),
        sa.CheckConstraint(
            "length(trim(registration_number)) > 0",
            name="ck_supplier_identity_claims_registration_required",
        ),
    )
    op.create_index(
        "ix_supplier_identity_claims_run_observation",
        "supplier_identity_claims",
        ["research_run_id", "price_observation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_supplier_identity_claims_run_observation",
        table_name="supplier_identity_claims",
    )
    op.drop_table("supplier_identity_claims")
