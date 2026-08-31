from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class EvidenceClass(StrEnum):
    FACT = "FACT"
    ESTIMATE = "ESTIMATE"
    ASSUMPTION = "ASSUMPTION"
    DERIVED_CALCULATION = "DERIVED_CALCULATION"
    AI_INFERENCE = "AI_INFERENCE"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ScenarioName(StrEnum):
    OPTIMISTIC = "OPTIMISTIC"
    BASE = "BASE"
    CONSERVATIVE = "CONSERVATIVE"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise ValueError("money amount must be finite")
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)


@dataclass(frozen=True, slots=True)
class Evidence:
    classification: EvidenceClass
    source_name: str
    source_url: str
    retrieved_at: datetime
    raw_value: str
    confidence: Confidence
    transformation: str | None = None

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if not self.source_name.strip():
            raise ValueError("source_name is required")
        if not self.source_url.startswith(("https://", "http://")):
            raise ValueError("source_url must be HTTP(S)")
        if not self.raw_value.strip():
            raise ValueError("raw_value is required")


@dataclass(frozen=True, slots=True)
class PriceObservation:
    observation_id: str
    product_name: str
    unit_price: Money
    quantity: int
    evidence: Evidence
    supplier_name: str | None = None
    minimum_order_quantity: int | None = None
    incoterm: str | None = None
    product_variant: str | None = None
    market_layer: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.unit_price.amount < 0:
            raise ValueError("unit price cannot be negative")
        if self.minimum_order_quantity is not None and self.minimum_order_quantity <= 0:
            raise ValueError("minimum_order_quantity must be positive")


@dataclass(frozen=True, slots=True)
class FXRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    evidence: Evidence
    rate_type: str

    def __post_init__(self) -> None:
        base = self.base_currency.strip().upper()
        quote = self.quote_currency.strip().upper()
        if len(base) != 3 or len(quote) != 3:
            raise ValueError("FX currencies must be three-letter codes")
        if self.rate <= 0 or not self.rate.is_finite():
            raise ValueError("FX rate must be finite and positive")
        object.__setattr__(self, "base_currency", base)
        object.__setattr__(self, "quote_currency", quote)


@dataclass(frozen=True, slots=True)
class CostInput:
    code: str
    label_fa: str
    money: Money
    basis: str
    evidence_class: EvidenceClass
    note: str | None = None

    def __post_init__(self) -> None:
        if self.money.amount < 0:
            raise ValueError(f"cost {self.code} cannot be negative")
        if self.basis not in {"TOTAL", "PER_UNIT"}:
            raise ValueError("basis must be TOTAL or PER_UNIT")


@dataclass(frozen=True, slots=True)
class ScenarioInput:
    name: ScenarioName
    quantity: int
    purchase_unit_price: Money
    costs: tuple[CostInput, ...]
    target_currency: str
    fx_rates: tuple[FXRate, ...]
    purchase_price_multiplier: Decimal = Decimal("1")
    cost_multiplier: Decimal = Decimal("1")
    unexpected_cost_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.purchase_price_multiplier <= 0 or self.cost_multiplier <= 0:
            raise ValueError("scenario multipliers must be positive")
        if not Decimal("0") <= self.unexpected_cost_rate <= Decimal("1"):
            raise ValueError("unexpected_cost_rate must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CalculatedComponent:
    code: str
    label_fa: str
    amount: Money
    evidence_class: EvidenceClass
    formula: str


@dataclass(frozen=True, slots=True)
class LandedCostResult:
    name: ScenarioName
    quantity: int
    target_currency: str
    components: tuple[CalculatedComponent, ...]
    total: Money
    per_unit: Money


@dataclass(frozen=True, slots=True)
class ResearchCase:
    case_id: str
    request_text: str
    product_name: str
    quantity: int
    destination: str
    observations: tuple[PriceObservation, ...]
    scenarios: tuple[ScenarioInput, ...]
    assumptions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("case quantity must be positive")
        if not self.scenarios:
            raise ValueError("at least one scenario is required")
