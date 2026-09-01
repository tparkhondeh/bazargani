from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from trade_agent.domain.models import (
    PriceObservation,
    ProductMatch,
    ProductMatchClass,
    ResearchCase,
)

PRODUCT_MATCH_POLICY_VERSION = "2026-08-31.1"
COMPARABLE_NAME_THRESHOLD = Decimal("0.60")
SIMILAR_NAME_THRESHOLD = Decimal("0.35")
ATTRIBUTE_AGREEMENT_THRESHOLD = Decimal("0.50")

_PERSIAN_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
    }
)
_NON_WORD = re.compile(r"[^\w]+", flags=re.UNICODE)


def normalize_product_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(_PERSIAN_TRANSLATION).casefold()
    return " ".join(_NON_WORD.sub(" ", normalized).split())


def _tokens(value: str) -> frozenset[str]:
    return frozenset(normalize_product_text(value).split())


def _name_similarity(requested: str, observed: str) -> Decimal:
    requested_tokens = _tokens(requested)
    observed_tokens = _tokens(observed)
    if not requested_tokens or not observed_tokens:
        return Decimal("0")
    intersection = len(requested_tokens & observed_tokens)
    union = len(requested_tokens | observed_tokens)
    return Decimal(intersection) / Decimal(union)


def _normalized_attributes(values: dict[str, str]) -> dict[str, str]:
    return {
        normalize_product_text(str(key)): normalize_product_text(str(value))
        for key, value in values.items()
    }


def _raw_candidate_attributes(observation: PriceObservation) -> dict[str, str]:
    attributes = dict(observation.product_attributes)
    if observation.product_variant and "variant" not in {
        normalize_product_text(key) for key in attributes
    }:
        attributes["variant"] = observation.product_variant
    return attributes


def _score(
    *,
    name_similarity: Decimal,
    requested_count: int,
    matched_count: int,
    supplied_count: int,
    conflict_count: int,
) -> int:
    if requested_count == 0:
        raw = name_similarity * Decimal("100")
    else:
        agreement = Decimal(matched_count) / Decimal(requested_count)
        coverage = Decimal(supplied_count) / Decimal(requested_count)
        raw = (
            name_similarity * Decimal("60")
            + agreement * Decimal("30")
            + coverage * Decimal("10")
            - Decimal(conflict_count) * Decimal("20")
        )
    bounded = min(Decimal("100"), max(Decimal("0"), raw))
    return int(bounded.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def match_price_observation(case: ResearchCase, observation: PriceObservation) -> ProductMatch:
    requested_name = normalize_product_text(case.product_name)
    observed_name = normalize_product_text(observation.product_name)
    name_exact = requested_name == observed_name
    name_similarity = _name_similarity(case.product_name, observation.product_name)
    requested = _normalized_attributes(case.product_attributes)
    raw_candidate = _raw_candidate_attributes(observation)
    candidate = _normalized_attributes(raw_candidate)

    matched = tuple(
        sorted(key for key, value in requested.items() if candidate.get(key) == value)
    )
    conflicting = tuple(
        sorted(
            key
            for key, value in requested.items()
            if key in candidate and candidate[key] != value
        )
    )
    missing = tuple(sorted(key for key in requested if key not in candidate))
    supplied_count = len(matched) + len(conflicting)
    agreement = (
        Decimal(len(matched)) / Decimal(len(requested)) if requested else Decimal("1")
    )

    if name_exact and requested and not conflicting and not missing:
        classification = ProductMatchClass.EXACT_VARIANT
    elif name_exact and not conflicting:
        classification = ProductMatchClass.EXACT_PRODUCT
    elif (
        name_similarity >= COMPARABLE_NAME_THRESHOLD
        and agreement >= ATTRIBUTE_AGREEMENT_THRESHOLD
        and not conflicting
    ):
        classification = ProductMatchClass.COMPARABLE
    elif (
        name_exact
        or name_similarity >= SIMILAR_NAME_THRESHOLD
        or (name_similarity > 0 and bool(matched))
    ):
        classification = ProductMatchClass.SIMILAR
    else:
        classification = ProductMatchClass.SUBSTITUTE

    explanations: list[str] = []
    if name_exact:
        explanations.append("نام نرمال‌شده محصول دقیقاً یکسان است.")
    else:
        explanations.append(f"شباهت واژگانی نام محصول {name_similarity:.2f} است.")
    if matched:
        explanations.append(f"ویژگی‌های منطبق: {', '.join(matched)}.")
    if conflicting:
        explanations.append(f"ویژگی‌های متعارض: {', '.join(conflicting)}.")
    if missing:
        explanations.append(f"ویژگی‌های بررسی‌نشده: {', '.join(missing)}.")
    if not requested:
        explanations.append("ویژگی مرجع برای تشخیص دقیق واریانت ثبت نشده است.")

    return ProductMatch(
        observation_id=observation.observation_id,
        classification=classification,
        score=_score(
            name_similarity=name_similarity,
            requested_count=len(requested),
            matched_count=len(matched),
            supplied_count=supplied_count,
            conflict_count=len(conflicting),
        ),
        name_similarity=name_similarity.quantize(Decimal("0.0001")),
        requested_attributes=dict(case.product_attributes),
        observed_attributes=raw_candidate,
        matched_attributes=matched,
        conflicting_attributes=conflicting,
        missing_attributes=missing,
        explanation_fa=tuple(explanations),
        policy_version=PRODUCT_MATCH_POLICY_VERSION,
    )


def match_research_case(case: ResearchCase) -> tuple[ProductMatch, ...]:
    return tuple(match_price_observation(case, observation) for observation in case.observations)
