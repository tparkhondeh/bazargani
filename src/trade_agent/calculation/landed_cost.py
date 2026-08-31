from __future__ import annotations

from collections import deque
from decimal import ROUND_HALF_UP, Decimal

from trade_agent.domain.models import (
    CalculatedComponent,
    EvidenceClass,
    FXRate,
    LandedCostResult,
    Money,
    ScenarioInput,
)

MONEY_QUANTUM = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def convert(amount: Money, target_currency: str, rates: tuple[FXRate, ...]) -> Money:
    target = target_currency.upper()
    if amount.currency == target:
        return Money(_round_money(amount.amount), target)

    graph: dict[str, list[tuple[str, Decimal]]] = {}
    for fx in rates:
        graph.setdefault(fx.base_currency, []).append((fx.quote_currency, fx.rate))
        graph.setdefault(fx.quote_currency, []).append((fx.base_currency, Decimal("1") / fx.rate))

    queue: deque[tuple[str, Decimal]] = deque([(amount.currency, Decimal("1"))])
    visited = {amount.currency}
    while queue:
        currency, cumulative = queue.popleft()
        for next_currency, rate in graph.get(currency, []):
            if next_currency in visited:
                continue
            next_cumulative = cumulative * rate
            if next_currency == target:
                return Money(_round_money(amount.amount * next_cumulative), target)
            visited.add(next_currency)
            queue.append((next_currency, next_cumulative))
    raise ValueError(f"no FX path from {amount.currency} to {target}")


def calculate_landed_cost(scenario: ScenarioInput) -> LandedCostResult:
    currency = scenario.target_currency.upper()
    purchase_unit = convert(scenario.purchase_unit_price, currency, scenario.fx_rates)
    purchase_total = _round_money(
        purchase_unit.amount * scenario.purchase_price_multiplier * scenario.quantity
    )
    components: list[CalculatedComponent] = [
        CalculatedComponent(
            code="product_cost",
            label_fa="هزینه خرید کالا",
            amount=Money(purchase_total, currency),
            evidence_class=EvidenceClass.DERIVED_CALCULATION,
            formula="converted unit price × purchase multiplier × quantity",
        )
    ]

    for cost in scenario.costs:
        normalized = convert(cost.money, currency, scenario.fx_rates).amount
        basis_amount = normalized * scenario.quantity if cost.basis == "PER_UNIT" else normalized
        adjusted = _round_money(basis_amount * scenario.cost_multiplier)
        components.append(
            CalculatedComponent(
                code=cost.code,
                label_fa=cost.label_fa,
                amount=Money(adjusted, currency),
                evidence_class=cost.evidence_class,
                formula=f"FX conversion × {cost.basis.lower()} basis × cost multiplier",
            )
        )

    subtotal = sum((item.amount.amount for item in components), Decimal("0"))
    if scenario.unexpected_cost_rate:
        contingency = _round_money(subtotal * scenario.unexpected_cost_rate)
        components.append(
            CalculatedComponent(
                code="unexpected_cost",
                label_fa="ذخیره هزینه پیش‌بینی‌نشده",
                amount=Money(contingency, currency),
                evidence_class=EvidenceClass.ASSUMPTION,
                formula="subtotal × unexpected cost rate",
            )
        )

    total_amount = _round_money(sum((c.amount.amount for c in components), Decimal("0")))
    per_unit_amount = _round_money(total_amount / scenario.quantity)
    return LandedCostResult(
        name=scenario.name,
        quantity=scenario.quantity,
        target_currency=currency,
        components=tuple(components),
        total=Money(total_amount, currency),
        per_unit=Money(per_unit_amount, currency),
    )
