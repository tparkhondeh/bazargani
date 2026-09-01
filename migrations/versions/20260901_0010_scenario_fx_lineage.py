"""Associate every persisted FX input with its landed-cost scenario."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0010"
down_revision: str | None = "20260901_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_fx_run_pair_type_effective",
        "fx_rates",
        type_="unique",
    )
    op.add_column(
        "fx_rates",
        sa.Column("scenario_id", sa.String(36), nullable=True),
    )

    connection = op.get_bind()
    rates = list(
        connection.execute(
            sa.text(
                """
                SELECT id, research_run_id, evidence_id, base_currency, quote_currency,
                       rate, rate_type, effective_at
                FROM fx_rates
                ORDER BY id
                """
            )
        ).mappings()
    )
    for rate in rates:
        scenario_ids = list(
            connection.scalars(
                sa.text(
                    """
                    SELECT id
                    FROM landed_cost_scenarios
                    WHERE research_run_id = :research_run_id
                    ORDER BY CASE name
                        WHEN 'OPTIMISTIC' THEN 0
                        WHEN 'BASE' THEN 1
                        WHEN 'CONSERVATIVE' THEN 2
                        ELSE 3
                    END, id
                    """
                ),
                {"research_run_id": rate["research_run_id"]},
            )
        )
        if not scenario_ids:
            raise RuntimeError("persisted FX rate has no landed-cost scenario")
        connection.execute(
            sa.text("UPDATE fx_rates SET scenario_id = :scenario_id WHERE id = :id"),
            {"scenario_id": scenario_ids[0], "id": rate["id"]},
        )
        for scenario_id in scenario_ids[1:]:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO fx_rates (
                        id, research_run_id, scenario_id, evidence_id, base_currency,
                        quote_currency, rate, rate_type, effective_at
                    ) VALUES (
                        :id, :research_run_id, :scenario_id, :evidence_id, :base_currency,
                        :quote_currency, :rate, :rate_type, :effective_at
                    )
                    """
                ),
                {
                    **rate,
                    "id": str(uuid4()),
                    "scenario_id": scenario_id,
                },
            )

    op.alter_column("fx_rates", "scenario_id", nullable=False)
    op.create_foreign_key(
        "fk_fx_rates_scenario_id",
        "fx_rates",
        "landed_cost_scenarios",
        ["scenario_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_fx_scenario_pair_type_effective",
        "fx_rates",
        ["scenario_id", "base_currency", "quote_currency", "rate_type", "effective_at"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_index("ix_fx_rates_scenario", "fx_rates", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_fx_rates_scenario", table_name="fx_rates")
    op.drop_constraint(
        "uq_fx_scenario_pair_type_effective",
        "fx_rates",
        type_="unique",
    )
    op.drop_constraint("fk_fx_rates_scenario_id", "fx_rates", type_="foreignkey")

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM fx_rates
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY research_run_id, base_currency, quote_currency,
                                     rate_type, effective_at
                        ORDER BY id
                    ) AS duplicate_number
                    FROM fx_rates
                ) AS ranked
                WHERE duplicate_number > 1
            )
            """
        )
    )
    op.drop_column("fx_rates", "scenario_id")
    op.create_unique_constraint(
        "uq_fx_run_pair_type_effective",
        "fx_rates",
        [
            "research_run_id",
            "base_currency",
            "quote_currency",
            "rate_type",
            "effective_at",
        ],
    )
