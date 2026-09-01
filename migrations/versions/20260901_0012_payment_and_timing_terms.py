"""Add structured payment, quote-validity, and lead-time fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0012"
down_revision: str | None = "20260901_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_observations",
        sa.Column("payment_terms", sa.String(500), nullable=True),
    )
    op.add_column(
        "price_observations",
        sa.Column("payment_method", sa.String(100), nullable=True),
    )
    op.add_column(
        "price_observations",
        sa.Column("quote_valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "price_observations",
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_price_observations_lead_time_days_positive",
        "price_observations",
        "lead_time_days IS NULL OR lead_time_days > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_price_observations_lead_time_days_positive",
        "price_observations",
        type_="check",
    )
    op.drop_column("price_observations", "lead_time_days")
    op.drop_column("price_observations", "quote_valid_until")
    op.drop_column("price_observations", "payment_method")
    op.drop_column("price_observations", "payment_terms")
