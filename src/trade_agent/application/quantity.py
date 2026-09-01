from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from trade_agent.domain.errors import PublicInputError

PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class QuantityPricePoint:
    observation_id: str
    supplier_name: str | None
    product_name: str
    product_variant: str | None
    product_group_key: str
    comparison_group: str
    quoted_quantity: int
    minimum_order_quantity: int | None
    eligible_for_requested_quantity: bool
    original_amount: Decimal
    original_currency: str
    normalized_amount: Decimal | None
    normalized_currency: str | None
    source_name: str
    source_url: str


@dataclass(frozen=True, slots=True)
class QuantityTierPoint:
    observation_id: str
    quoted_quantity: int
    minimum_order_quantity: int | None
    eligible_for_requested_quantity: bool
    original_amount: Decimal
    original_currency: str
    normalized_amount: Decimal | None
    normalized_currency: str | None
    normalized_change_from_previous_percent: Decimal | None
    source_name: str
    source_url: str


@dataclass(frozen=True, slots=True)
class QuantityOfferSeries:
    supplier_name: str | None
    product_name: str
    product_variant: str | None
    comparison_group: str
    points: tuple[QuantityTierPoint, ...]


@dataclass(frozen=True, slots=True)
class QuantityAnalysis:
    status: str
    requested_quantity: int
    series: tuple[QuantityOfferSeries, ...]
    economic_order_range_min: int | None
    economic_order_range_max: int | None
    limitations: tuple[str, ...]


def quantity_product_key(
    product_name: str,
    product_variant: str | None,
    product_attributes: dict[str, str],
) -> str:
    return json.dumps(
        {
            "name": product_name,
            "variant": product_variant,
            "attributes": product_attributes,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def analyze_quantity_points(
    requested_quantity: int,
    points: tuple[QuantityPricePoint, ...],
) -> QuantityAnalysis:
    if requested_quantity <= 0:
        raise PublicInputError("requested quantity must be positive")

    grouped: dict[tuple[str, str, str], list[QuantityPricePoint]] = {}
    for point in points:
        supplier_key = point.supplier_name or f"anonymous:{point.observation_id}"
        grouped.setdefault(
            (supplier_key, point.product_group_key, point.comparison_group),
            [],
        ).append(point)

    series: list[QuantityOfferSeries] = []
    has_comparable_price = False
    for (_supplier_key, _product_key, comparison_group), group in sorted(
        grouped.items()
    ):
        ordered = sorted(group, key=lambda point: (point.quoted_quantity, point.observation_id))
        tier_points: list[QuantityTierPoint] = []
        previous: Decimal | None = None
        for point in ordered:
            change: Decimal | None = None
            if point.normalized_amount is not None:
                has_comparable_price = True
                if previous is not None and previous != 0:
                    change = (
                        (point.normalized_amount - previous)
                        / previous
                        * Decimal("100")
                    ).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
                previous = point.normalized_amount
            else:
                previous = None
            tier_points.append(
                QuantityTierPoint(
                    observation_id=point.observation_id,
                    quoted_quantity=point.quoted_quantity,
                    minimum_order_quantity=point.minimum_order_quantity,
                    eligible_for_requested_quantity=point.eligible_for_requested_quantity,
                    original_amount=point.original_amount,
                    original_currency=point.original_currency,
                    normalized_amount=point.normalized_amount,
                    normalized_currency=point.normalized_currency,
                    normalized_change_from_previous_percent=change,
                    source_name=point.source_name,
                    source_url=point.source_url,
                )
            )
        series.append(
            QuantityOfferSeries(
                supplier_name=ordered[0].supplier_name,
                product_name=ordered[0].product_name,
                product_variant=ordered[0].product_variant,
                comparison_group=comparison_group,
                points=tuple(tier_points),
            )
        )

    if not points:
        status = "NO_OBSERVED_QUOTES"
    elif not has_comparable_price:
        status = "NO_COMPARABLE_PRICES"
    else:
        status = "OBSERVED_QUOTES_ONLY"
    return QuantityAnalysis(
        status=status,
        requested_quantity=requested_quantity,
        series=tuple(series),
        economic_order_range_min=None,
        economic_order_range_max=None,
        limitations=(
            "quoted quantity points are observations, not guaranteed continuous price tiers",
            "economic order range requires demand, ordering, holding, lead-time, "
            "and service inputs",
            "supplier capacity and negotiation margin remain unverified without evidence",
        ),
    )
