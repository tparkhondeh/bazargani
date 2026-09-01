"""Add structured named-place and version fields to Incoterm declarations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0011"
down_revision: str | None = "20260901_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_observations",
        sa.Column("incoterm_named_place", sa.String(300), nullable=True),
    )
    op.add_column(
        "price_observations",
        sa.Column("incoterm_version", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_observations", "incoterm_version")
    op.drop_column("price_observations", "incoterm_named_place")

