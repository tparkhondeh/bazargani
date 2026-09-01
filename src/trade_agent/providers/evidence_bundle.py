from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from trade_agent.domain.errors import PublicInputError
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
    SupplierIdentityClaim,
)

MAX_OBSERVATIONS = 500
MAX_FX_RATES = 100
MAX_SCENARIOS = 3
MAX_COSTS_PER_SCENARIO = 100
MAX_NOTES_PER_KIND = 200
MAX_NOTE_LENGTH = 5000
MAX_PRODUCT_ATTRIBUTES = 100
MAX_SUPPLIER_IDENTITY_CLAIMS = 500


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PublicInputError(f"{label} must be an object")
    return value


def _object_list(value: Any, label: str, maximum: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise PublicInputError(f"{label} must be an array")
    if len(value) > maximum:
        raise PublicInputError(f"{label} cannot contain more than {maximum} items")
    return [_object(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _text_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PublicInputError(f"{label} must be an array")
    if len(value) > MAX_NOTES_PER_KIND:
        raise PublicInputError(
            f"{label} cannot contain more than {MAX_NOTES_PER_KIND} items"
        )
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise PublicInputError(f"{label}[{index}] must be a string")
        text = item.strip()
        if not text:
            raise PublicInputError(f"{label}[{index}] cannot be empty")
        if len(text) > MAX_NOTE_LENGTH:
            raise PublicInputError(
                f"{label}[{index}] cannot exceed {MAX_NOTE_LENGTH} characters"
            )
        normalized.append(text)
    return tuple(normalized)


def _attributes(value: Any, label: str) -> dict[str, str]:
    attributes = _object(value, label)
    if len(attributes) > MAX_PRODUCT_ATTRIBUTES:
        raise PublicInputError(
            f"{label} cannot contain more than {MAX_PRODUCT_ATTRIBUTES} items"
        )
    return {str(key): str(item) for key, item in attributes.items()}


def _decimal(value: Any) -> Decimal:
    if isinstance(value, float):
        raise PublicInputError("JSON decimals must be strings or integers, never floats")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise PublicInputError("decimal values must contain a valid base-10 number") from None


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PublicInputError(f"{label} must be a string or null")
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise PublicInputError(f"{label} must be a string")
    if not value.strip():
        raise PublicInputError(f"{label} cannot be empty")
    return value


def _optional_positive_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise PublicInputError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise PublicInputError(f"{label} must be a positive integer") from None
    if parsed <= 0:
        raise PublicInputError(f"{label} must be a positive integer")
    return parsed


def _optional_datetime(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PublicInputError(f"{label} must be an ISO 8601 string or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PublicInputError(f"{label} must be a valid ISO 8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PublicInputError(f"{label} must include a timezone offset")
    return parsed


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


def _fx_rates(value: Any, label: str) -> tuple[FXRate, ...]:
    rate_items = _object_list(value, label, MAX_FX_RATES)
    return tuple(
        FXRate(
            base_currency=str(item["base_currency"]),
            quote_currency=str(item["quote_currency"]),
            rate=_decimal(item["rate"]),
            evidence=_evidence(_object(item["evidence"], f"{label} evidence")),
            rate_type=str(item["rate_type"]),
            effective_at=(
                datetime.fromisoformat(str(item["effective_at"]).replace("Z", "+00:00"))
                if item.get("effective_at")
                else None
            ),
        )
        for item in rate_items
    )


def load_evidence_bundle(path: Path) -> ResearchCase:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PublicInputError("evidence bundle root must be an object")
    return parse_evidence_bundle(raw)


def parse_evidence_bundle(raw: dict[str, Any]) -> ResearchCase:
    try:
        return _parse_evidence_bundle(raw)
    except KeyError as exc:
        raise PublicInputError(
            f"missing required evidence bundle field: {exc.args[0]}"
        ) from None


def _parse_evidence_bundle(raw: dict[str, Any]) -> ResearchCase:
    observation_items = _object_list(
        raw["observations"], "observations", MAX_OBSERVATIONS
    )
    observations = tuple(
        PriceObservation(
            observation_id=str(item["observation_id"]),
            product_name=str(item["product_name"]),
            unit_price=_money(_object(item["unit_price"], "observation unit_price")),
            quantity=int(item["quantity"]),
            unit=str(item["unit"]),
            evidence=_evidence(_object(item["evidence"], "observation evidence")),
            supplier_name=_optional_text(item.get("supplier_name"), "supplier_name"),
            minimum_order_quantity=_optional_positive_int(
                item.get("minimum_order_quantity"),
                "minimum_order_quantity",
            ),
            incoterm=_optional_text(item.get("incoterm"), "incoterm"),
            incoterm_named_place=_optional_text(
                item.get("incoterm_named_place"),
                "incoterm_named_place",
            ),
            incoterm_version=_optional_text(
                item.get("incoterm_version"),
                "incoterm_version",
            ),
            payment_terms=_optional_text(
                item.get("payment_terms"),
                "payment_terms",
            ),
            payment_method=_optional_text(
                item.get("payment_method"),
                "payment_method",
            ),
            quote_valid_until=_optional_datetime(
                item.get("quote_valid_until"),
                "quote_valid_until",
            ),
            lead_time_days=_optional_positive_int(
                item.get("lead_time_days"),
                "lead_time_days",
            ),
            product_variant=_optional_text(
                item.get("product_variant"),
                "product_variant",
            ),
            product_attributes=_attributes(
                item.get("product_attributes", {}),
                "observation product_attributes",
            ),
            market_layer=str(item.get("market_layer", "UNKNOWN")),
        )
        for item in observation_items
    )
    claim_items = _object_list(
        raw.get("supplier_identity_claims", []),
        "supplier_identity_claims",
        MAX_SUPPLIER_IDENTITY_CLAIMS,
    )
    supplier_identity_claims = tuple(
        SupplierIdentityClaim(
            claim_id=_required_text(
                item.get("claim_id"),
                f"supplier_identity_claims[{index}].claim_id",
            ),
            observation_id=_required_text(
                item.get("observation_id"),
                f"supplier_identity_claims[{index}].observation_id",
            ),
            claimed_legal_name=_required_text(
                item.get("claimed_legal_name"),
                f"supplier_identity_claims[{index}].claimed_legal_name",
            ),
            jurisdiction=_required_text(
                item.get("jurisdiction"),
                f"supplier_identity_claims[{index}].jurisdiction",
            ),
            registration_number=_required_text(
                item.get("registration_number"),
                f"supplier_identity_claims[{index}].registration_number",
            ),
            evidence=_evidence(
                _object(
                    item["evidence"],
                    f"supplier_identity_claims[{index}].evidence",
                )
            ),
        )
        for index, item in enumerate(claim_items)
    )
    shared_rates = _fx_rates(raw.get("fx_rates", []), "fx_rates")
    scenario_items = _object_list(raw["scenarios"], "scenarios", MAX_SCENARIOS)
    scenarios = tuple(
        ScenarioInput(
            name=ScenarioName(item["name"]),
            quantity=int(item.get("quantity", raw["quantity"])),
            purchase_unit_price=_money(
                _object(item["purchase_unit_price"], "scenario purchase_unit_price")
            ),
            costs=tuple(
                CostInput(
                    code=str(cost["code"]),
                    label_fa=str(cost["label_fa"]),
                    money=_money(_object(cost["money"], "cost money")),
                    basis=str(cost["basis"]),
                    evidence_class=EvidenceClass(cost["evidence_class"]),
                    note=cost.get("note"),
                )
                for cost in _object_list(
                    item["costs"],
                    "scenario costs",
                    MAX_COSTS_PER_SCENARIO,
                )
            ),
            target_currency=str(item["target_currency"]),
            fx_rates=(
                _fx_rates(item["fx_rates"], f"scenario {item['name']} fx_rates")
                if "fx_rates" in item
                else shared_rates
            ),
            purchase_price_multiplier=_decimal(item.get("purchase_price_multiplier", "1")),
            cost_multiplier=_decimal(item.get("cost_multiplier", "1")),
            unexpected_cost_rate=_decimal(item.get("unexpected_cost_rate", "0")),
        )
        for item in scenario_items
    )
    return ResearchCase(
        case_id=str(raw["case_id"]),
        request_text=str(raw["request_text"]),
        product_name=str(raw["product_name"]),
        quantity=int(raw["quantity"]),
        destination=str(raw["destination"]),
        observations=observations,
        scenarios=scenarios,
        supplier_identity_claims=supplier_identity_claims,
        assumptions=_text_list(raw.get("assumptions", []), "assumptions"),
        unknowns=_text_list(raw.get("unknowns", []), "unknowns"),
        product_attributes=_attributes(
            raw.get("product_attributes", {}), "product_attributes"
        ),
        metadata=_object(raw.get("metadata", {}), "metadata"),
    )
