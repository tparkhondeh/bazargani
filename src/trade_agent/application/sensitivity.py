from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from trade_agent.domain.errors import PublicInputError
from trade_agent.domain.models import LandedCostResult, ScenarioName

PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ScenarioCostPoint:
    name: str
    quantity: int
    target_currency: str
    per_unit_amount: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioSensitivity:
    status: str
    quantity: int | None
    target_currency: str | None
    optimistic_per_unit: Decimal | None
    base_per_unit: Decimal | None
    conservative_per_unit: Decimal | None
    optimistic_delta_from_base: Decimal | None
    optimistic_delta_percent: Decimal | None
    conservative_delta_from_base: Decimal | None
    conservative_delta_percent: Decimal | None
    range_per_unit: Decimal | None
    range_percent_of_base: Decimal | None
    limitations: tuple[str, ...]


def cost_points(results: tuple[LandedCostResult, ...]) -> tuple[ScenarioCostPoint, ...]:
    return tuple(
        ScenarioCostPoint(
            name=result.name.value,
            quantity=result.quantity,
            target_currency=result.target_currency,
            per_unit_amount=result.per_unit.amount,
        )
        for result in results
    )


def analyze_scenario_sensitivity(
    points: tuple[ScenarioCostPoint, ...],
) -> ScenarioSensitivity:
    by_name = {point.name: point for point in points}
    required = {name.value for name in ScenarioName}
    if set(by_name) != required or len(points) != len(required):
        raise PublicInputError("sensitivity requires exactly one of each scenario")

    quantities = {point.quantity for point in points}
    currencies = {point.target_currency for point in points}
    if len(quantities) != 1 or len(currencies) != 1:
        return ScenarioSensitivity(
            status="MIXED_BASIS",
            quantity=None,
            target_currency=None,
            optimistic_per_unit=None,
            base_per_unit=None,
            conservative_per_unit=None,
            optimistic_delta_from_base=None,
            optimistic_delta_percent=None,
            conservative_delta_from_base=None,
            conservative_delta_percent=None,
            range_per_unit=None,
            range_percent_of_base=None,
            limitations=(
                "scenario quantity and target currency must match before sensitivity comparison",
            ),
        )

    optimistic = by_name[ScenarioName.OPTIMISTIC.value].per_unit_amount
    base = by_name[ScenarioName.BASE.value].per_unit_amount
    conservative = by_name[ScenarioName.CONSERVATIVE.value].per_unit_amount
    values = (optimistic, base, conservative)
    range_per_unit = max(values) - min(values)
    quantity = quantities.pop()
    target_currency = currencies.pop()
    optimistic_delta = optimistic - base
    conservative_delta = conservative - base
    if base == 0:
        return ScenarioSensitivity(
            status="ZERO_BASE",
            quantity=quantity,
            target_currency=target_currency,
            optimistic_per_unit=optimistic,
            base_per_unit=base,
            conservative_per_unit=conservative,
            optimistic_delta_from_base=optimistic_delta,
            optimistic_delta_percent=None,
            conservative_delta_from_base=conservative_delta,
            conservative_delta_percent=None,
            range_per_unit=range_per_unit,
            range_percent_of_base=None,
            limitations=("percentage sensitivity is undefined when base per-unit cost is zero",),
        )

    def percent(value: Decimal) -> Decimal:
        return (value / base * Decimal("100")).quantize(
            PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    return ScenarioSensitivity(
        status="COMPARABLE",
        quantity=quantity,
        target_currency=target_currency,
        optimistic_per_unit=optimistic,
        base_per_unit=base,
        conservative_per_unit=conservative,
        optimistic_delta_from_base=optimistic_delta,
        optimistic_delta_percent=percent(optimistic_delta),
        conservative_delta_from_base=conservative_delta,
        conservative_delta_percent=percent(conservative_delta),
        range_per_unit=range_per_unit,
        range_percent_of_base=percent(range_per_unit),
        limitations=(
            "scenario deltas combine every submitted price, cost, and contingency assumption",
            "this comparison is not an economic order quantity calculation",
        ),
    )
