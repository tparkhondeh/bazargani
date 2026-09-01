from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from trade_agent.domain.errors import PublicInputError

MONEY_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class DistributionPricePoint:
    observation_id: str
    product_name: str
    product_variant: str | None
    product_group_key: str
    market_layer: str
    comparison_group: str
    quoted_quantity: int
    normalized_amount: Decimal | None
    normalized_currency: str | None
    source_url: str


@dataclass(frozen=True, slots=True)
class PriceDistributionGroup:
    product_name: str
    product_variant: str | None
    market_layer: str
    comparison_group: str
    quoted_quantity: int
    normalized_currency: str
    observation_ids: tuple[str, ...]
    observation_count: int
    distinct_source_count: int
    minimum_amount: Decimal
    median_amount: Decimal
    maximum_amount: Decimal
    range_amount: Decimal


@dataclass(frozen=True, slots=True)
class PriceDistribution:
    status: str
    groups: tuple[PriceDistributionGroup, ...]
    excluded_observation_ids: tuple[str, ...]
    limitations: tuple[str, ...]


def _median(values: list[Decimal]) -> Decimal:
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return ((values[midpoint - 1] + values[midpoint]) / Decimal("2")).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def analyze_price_distribution(
    points: tuple[DistributionPricePoint, ...],
) -> PriceDistribution:
    if any(point.quoted_quantity <= 0 for point in points):
        raise PublicInputError("distribution point quantity must be positive")

    grouped: dict[tuple[str, str, str, int], list[DistributionPricePoint]] = {}
    excluded: list[str] = []
    for point in points:
        if point.normalized_amount is None or point.normalized_currency is None:
            excluded.append(point.observation_id)
            continue
        key = (
            point.product_group_key,
            point.market_layer,
            point.comparison_group,
            point.quoted_quantity,
        )
        grouped.setdefault(key, []).append(point)

    groups: list[PriceDistributionGroup] = []
    for (_product_key, market_layer, comparison_group, quantity), group in sorted(
        grouped.items()
    ):
        currencies = {point.normalized_currency for point in group}
        if len(currencies) != 1:
            raise PublicInputError("distribution group must have one normalized currency")
        normalized_currency = next(iter(currencies))
        if normalized_currency is None:
            raise PublicInputError("distribution group must have a normalized currency")
        amounts = sorted(
            point.normalized_amount
            for point in group
            if point.normalized_amount is not None
        )
        ordered_ids = tuple(sorted(point.observation_id for point in group))
        groups.append(
            PriceDistributionGroup(
                product_name=group[0].product_name,
                product_variant=group[0].product_variant,
                market_layer=market_layer,
                comparison_group=comparison_group,
                quoted_quantity=quantity,
                normalized_currency=normalized_currency,
                observation_ids=ordered_ids,
                observation_count=len(group),
                distinct_source_count=len({point.source_url for point in group}),
                minimum_amount=amounts[0],
                median_amount=_median(amounts),
                maximum_amount=amounts[-1],
                range_amount=amounts[-1] - amounts[0],
            )
        )

    if not points:
        status = "NO_OBSERVED_PRICES"
    elif not groups:
        status = "NO_COMPARABLE_PRICES"
    else:
        status = "OBSERVED_DISTRIBUTIONS"
    return PriceDistribution(
        status=status,
        groups=tuple(groups),
        excluded_observation_ids=tuple(sorted(excluded)),
        limitations=(
            "distribution covers only retained observations in this research run",
            "market-layer labels do not prove benchmark representativeness or source approval",
            "different products, quantities, units, currencies, and market layers remain separate",
        ),
    )
