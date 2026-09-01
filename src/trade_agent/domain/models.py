from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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


class ProductMatchClass(StrEnum):
    EXACT_PRODUCT = "EXACT_PRODUCT"
    EXACT_VARIANT = "EXACT_VARIANT"
    COMPARABLE = "COMPARABLE"
    SIMILAR = "SIMILAR"
    SUBSTITUTE = "SUBSTITUTE"


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
    unit: str
    evidence: Evidence
    supplier_name: str | None = None
    minimum_order_quantity: int | None = None
    incoterm: str | None = None
    incoterm_named_place: str | None = None
    incoterm_version: str | None = None
    payment_terms: str | None = None
    payment_method: str | None = None
    quote_valid_until: datetime | None = None
    lead_time_days: int | None = None
    product_variant: str | None = None
    product_attributes: dict[str, str] = field(default_factory=dict)
    market_layer: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if not self.product_name.strip():
            raise ValueError("price observation product_name is required")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.unit_price.amount < 0:
            raise ValueError("unit price cannot be negative")
        if self.minimum_order_quantity is not None and self.minimum_order_quantity <= 0:
            raise ValueError("minimum_order_quantity must be positive")
        unit = self.unit.strip().upper()
        if not unit or len(unit) > 50 or any(ord(character) < 32 for character in unit):
            raise ValueError("price observation unit must be a non-empty safe value")
        object.__setattr__(self, "unit", unit)
        incoterm = self.incoterm.strip().upper() if self.incoterm is not None else None
        if incoterm == "":
            incoterm = None
        if incoterm is not None and (
            len(incoterm) > 10 or any(ord(character) < 32 for character in incoterm)
        ):
            raise ValueError("incoterm must be a safe code of at most 10 characters")
        object.__setattr__(self, "incoterm", incoterm)
        named_place = (
            self.incoterm_named_place.strip()
            if self.incoterm_named_place is not None
            else None
        )
        if named_place == "":
            named_place = None
        if named_place is not None and (
            len(named_place) > 300
            or any(ord(character) < 32 for character in named_place)
        ):
            raise ValueError(
                "incoterm_named_place must be a safe value of at most 300 characters"
            )
        object.__setattr__(self, "incoterm_named_place", named_place)
        version = (
            self.incoterm_version.strip()
            if self.incoterm_version is not None
            else None
        )
        if version == "":
            version = None
        if version is not None and (
            len(version) > 20 or any(ord(character) < 32 for character in version)
        ):
            raise ValueError(
                "incoterm_version must be a safe value of at most 20 characters"
            )
        object.__setattr__(self, "incoterm_version", version)
        payment_terms = self.payment_terms.strip() if self.payment_terms is not None else None
        if payment_terms == "":
            payment_terms = None
        if payment_terms is not None and (
            len(payment_terms) > 500
            or any(ord(character) < 32 for character in payment_terms)
        ):
            raise ValueError("payment_terms must be a safe value of at most 500 characters")
        object.__setattr__(self, "payment_terms", payment_terms)
        payment_method = (
            self.payment_method.strip() if self.payment_method is not None else None
        )
        if payment_method == "":
            payment_method = None
        if payment_method is not None and (
            len(payment_method) > 100
            or any(ord(character) < 32 for character in payment_method)
        ):
            raise ValueError("payment_method must be a safe value of at most 100 characters")
        object.__setattr__(self, "payment_method", payment_method)
        if self.quote_valid_until is not None:
            if (
                self.quote_valid_until.tzinfo is None
                or self.quote_valid_until.utcoffset() is None
            ):
                raise ValueError("quote_valid_until must be timezone-aware")
            object.__setattr__(
                self,
                "quote_valid_until",
                self.quote_valid_until.astimezone(UTC),
            )
        if self.lead_time_days is not None and (
            isinstance(self.lead_time_days, bool) or self.lead_time_days <= 0
        ):
            raise ValueError("lead_time_days must be a positive integer")
        invalid_attributes = (
            not str(key).strip() or not str(value).strip()
            for key, value in self.product_attributes.items()
        )
        if any(invalid_attributes):
            raise ValueError("product attribute keys and values must be non-empty")


@dataclass(frozen=True, slots=True)
class ProductMatch:
    observation_id: str
    classification: ProductMatchClass
    score: int
    name_similarity: Decimal
    requested_attributes: dict[str, str]
    observed_attributes: dict[str, str]
    matched_attributes: tuple[str, ...]
    conflicting_attributes: tuple[str, ...]
    missing_attributes: tuple[str, ...]
    explanation_fa: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("product match score must be between 0 and 100")
        if not Decimal("0") <= self.name_similarity <= Decimal("1"):
            raise ValueError("name similarity must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SupplierOfferRanking:
    observation_id: str
    supplier_name: str | None
    comparison_group: str
    rank: int | None
    eligible_for_quantity: bool
    rankable: bool
    normalized_unit_price: Money | None
    total_score: int
    component_scores: dict[str, int]
    unknown_factors: tuple[str, ...]
    explanation_fa: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if not 0 <= self.total_score <= 100:
            raise ValueError("supplier offer score must be between 0 and 100")
        if self.rank is not None and self.rank <= 0:
            raise ValueError("supplier offer rank must be positive")
        if self.rankable and self.rank is None:
            raise ValueError("a rankable supplier offer must have a rank")
        if not self.rankable and self.rank is not None:
            raise ValueError("an unrankable supplier offer cannot have a rank")


@dataclass(frozen=True, slots=True)
class FXRate:
    base_currency: str
    quote_currency: str
    rate: Decimal
    evidence: Evidence
    rate_type: str
    effective_at: datetime | None = None

    def __post_init__(self) -> None:
        base = self.base_currency.strip().upper()
        quote = self.quote_currency.strip().upper()
        if len(base) != 3 or len(quote) != 3:
            raise ValueError("FX currencies must be three-letter codes")
        if self.rate <= 0 or not self.rate.is_finite():
            raise ValueError("FX rate must be finite and positive")
        if self.effective_at is not None and self.effective_at.tzinfo is None:
            raise ValueError("effective_at must be timezone-aware")
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
    product_attributes: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required_text = (self.case_id, self.product_name, self.destination)
        if not all(value.strip() for value in required_text):
            raise ValueError("case_id, product_name, and destination are required")
        if self.quantity <= 0:
            raise ValueError("case quantity must be positive")
        if not self.scenarios:
            raise ValueError("at least one scenario is required")
        observation_ids = [observation.observation_id for observation in self.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation_id values must be unique within a research case")
        invalid_attributes = (
            not str(key).strip() or not str(value).strip()
            for key, value in self.product_attributes.items()
        )
        if any(invalid_attributes):
            raise ValueError("requested product attribute keys and values must be non-empty")
