from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trade_agent.domain.models import (
    Confidence,
    CostInput,
    Evidence,
    EvidenceClass,
    FXRate,
    Money,
    PriceObservation,
    ResearchCase,
    ScenarioInput,
    ScenarioName,
)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, float):
        raise ValueError("JSON decimals must be strings or integers, never floats")
    return Decimal(str(value))


def _evidence(data: dict[str, Any]) -> Evidence:
    return Evidence(
        classification=EvidenceClass(data["classification"]),
        source_name=str(data["source_name"]),
        source_url=str(data["source_url"]),
        retrieved_at=datetime.fromisoformat(str(data["retrieved_at"]).replace("Z", "+00:00")),
        raw_value=str(data["raw_value"]),
        confidence=Confidence(data.get("confidence", "UNKNOWN")),
        transformation=data.get("transformation"),
    )


def _money(data: dict[str, Any]) -> Money:
    return Money(amount=_decimal(data["amount"]), currency=str(data["currency"]))


def load_evidence_bundle(path: Path) -> ResearchCase:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("evidence bundle root must be an object")
    return parse_evidence_bundle(raw)


def parse_evidence_bundle(raw: dict[str, Any]) -> ResearchCase:
    observations = tuple(
        PriceObservation(
            observation_id=str(item["observation_id"]),
            product_name=str(item["product_name"]),
            unit_price=_money(item["unit_price"]),
            quantity=int(item["quantity"]),
            evidence=_evidence(item["evidence"]),
            supplier_name=item.get("supplier_name"),
            minimum_order_quantity=item.get("minimum_order_quantity"),
            incoterm=item.get("incoterm"),
            product_variant=item.get("product_variant"),
            market_layer=str(item.get("market_layer", "UNKNOWN")),
        )
        for item in raw["observations"]
    )
    rates = tuple(
        FXRate(
            base_currency=str(item["base_currency"]),
            quote_currency=str(item["quote_currency"]),
            rate=_decimal(item["rate"]),
            evidence=_evidence(item["evidence"]),
            rate_type=str(item["rate_type"]),
            effective_at=(
                datetime.fromisoformat(str(item["effective_at"]).replace("Z", "+00:00"))
                if item.get("effective_at")
                else None
            ),
        )
        for item in raw["fx_rates"]
    )
    scenarios = tuple(
        ScenarioInput(
            name=ScenarioName(item["name"]),
            quantity=int(item.get("quantity", raw["quantity"])),
            purchase_unit_price=_money(item["purchase_unit_price"]),
            costs=tuple(
                CostInput(
                    code=str(cost["code"]),
                    label_fa=str(cost["label_fa"]),
                    money=_money(cost["money"]),
                    basis=str(cost["basis"]),
                    evidence_class=EvidenceClass(cost["evidence_class"]),
                    note=cost.get("note"),
                )
                for cost in item["costs"]
            ),
            target_currency=str(item["target_currency"]),
            fx_rates=rates,
            purchase_price_multiplier=_decimal(item.get("purchase_price_multiplier", "1")),
            cost_multiplier=_decimal(item.get("cost_multiplier", "1")),
            unexpected_cost_rate=_decimal(item.get("unexpected_cost_rate", "0")),
        )
        for item in raw["scenarios"]
    )
    return ResearchCase(
        case_id=str(raw["case_id"]),
        request_text=str(raw["request_text"]),
        product_name=str(raw["product_name"]),
        quantity=int(raw["quantity"]),
        destination=str(raw["destination"]),
        observations=observations,
        scenarios=scenarios,
        assumptions=tuple(map(str, raw.get("assumptions", []))),
        unknowns=tuple(map(str, raw.get("unknowns", []))),
        metadata=dict(raw.get("metadata", {})),
    )
