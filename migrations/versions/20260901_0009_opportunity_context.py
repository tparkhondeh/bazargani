"""Add mutable workflow context to opportunities."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0009"
down_revision: str | None = "20260901_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("next_action", sa.String(500), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "notes")
    op.drop_column("opportunities", "deadline")
    op.drop_column("opportunities", "next_action")
