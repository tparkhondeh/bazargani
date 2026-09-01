from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from trade_agent.calculation.landed_cost import convert
from trade_agent.domain.models import (
    Confidence,
    EvidenceClass,
    Money,
    PriceObservation,
    ProductMatch,
    ProductMatchClass,
    ResearchCase,
    ScenarioInput,
    ScenarioName,
    SupplierOfferRanking,
)

SUPPLIER_RANKING_POLICY_VERSION = "2026-08-31.1"

_CONFIDENCE_POINTS = {
    Confidence.HIGH: 10,
    Confidence.MEDIUM: 7,
    Confidence.LOW: 3,
    Confidence.UNKNOWN: 0,
}
_EVIDENCE_CLASS_POINTS = {
    EvidenceClass.FACT: 10,
    EvidenceClass.ESTIMATE: 6,
    EvidenceClass.ASSUMPTION: 2,
    EvidenceClass.DERIVED_CALCULATION: 5,
    EvidenceClass.AI_INFERENCE: 1,
}


@dataclass(slots=True)
class _DraftRanking:
    observation: PriceObservation
    match: ProductMatch
    comparison_group: str
    eligible: bool
    rankable: bool
    normalized_unit_price: Money | None
    component_scores: dict[str, int]
    unknown_factors: list[str]
    explanations: list[str]
    total_score: int = 0
    rank: int | None = None


def _rounded_points(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _quantity_score(case: ResearchCase, observation: PriceObservation) -> tuple[bool, int]:
    if (
        observation.minimum_order_quantity is not None
        and case.quantity < observation.minimum_order_quantity
    ):
        return False, 0
    if observation.quantity == case.quantity:
        points = 10
    elif observation.quantity < case.quantity:
        points = 8
    else:
        points = 5
    if observation.minimum_order_quantity is None:
        points = min(points, 7)
    return True, points


def _terms_score(observation: PriceObservation) -> int:
    return sum(
        (
            4 if observation.supplier_name else 0,
            3 if observation.incoterm else 0,
            2 if observation.minimum_order_quantity is not None else 0,
            1 if observation.product_variant or observation.product_attributes else 0,
        )
    )


def _base_scenario(case: ResearchCase) -> ScenarioInput:
    return next(scenario for scenario in case.scenarios if scenario.name is ScenarioName.BASE)


def rank_supplier_offers(
    case: ResearchCase, matches: tuple[ProductMatch, ...]
) -> tuple[SupplierOfferRanking, ...]:
    match_by_observation = {match.observation_id: match for match in matches}
    if len(match_by_observation) != len(case.observations):
        raise ValueError("each retained price observation requires exactly one product match")
    base = _base_scenario(case)
    target_currency = base.target_currency.upper()
    drafts: list[_DraftRanking] = []

    for observation in case.observations:
        match = match_by_observation[observation.observation_id]
        eligible, quantity_points = _quantity_score(case, observation)
        unknown_factors = ["supplier_reliability", "certifications", "payment_terms"]
        explanations = [
            f"امتیاز تطبیق محصول {match.score}/100 است.",
            f"امتیاز سازگاری تعداد {quantity_points}/10 است.",
        ]
        if observation.minimum_order_quantity is None:
            unknown_factors.append("minimum_order_quantity")
            explanations.append("حداقل سفارش اعلام نشده است.")
        if not observation.supplier_name:
            unknown_factors.append("supplier_identity")
            explanations.append("هویت تأمین‌کننده ثبت نشده است.")
        if not observation.incoterm:
            unknown_factors.append("incoterm")
            explanations.append("Incoterm اعلام نشده است.")

        normalized_price: Money | None
        try:
            normalized_price = convert(
                observation.unit_price,
                target_currency,
                base.fx_rates,
            )
        except ValueError:
            normalized_price = None
            unknown_factors.append("comparable_fx_rate")
            explanations.append("مسیر تبدیل ارز برای مقایسه قیمت وجود ندارد.")

        rankable = bool(
            eligible
            and observation.supplier_name
            and normalized_price is not None
            and normalized_price.amount > 0
            and match.classification is not ProductMatchClass.SUBSTITUTE
            and not match.conflicting_attributes
        )
        component_scores = {
            "product_match": _rounded_points(Decimal(match.score) * Decimal("0.35")),
            "evidence_quality": (
                _CONFIDENCE_POINTS[observation.evidence.confidence]
                + _EVIDENCE_CLASS_POINTS[observation.evidence.classification]
            ),
            "quantity_fit": quantity_points,
            "commercial_completeness": _terms_score(observation),
            "price_competitiveness": 0,
        }
        drafts.append(
            _DraftRanking(
                observation=observation,
                match=match,
                comparison_group=f"{observation.unit}:{target_currency}",
                eligible=eligible,
                rankable=rankable,
                normalized_unit_price=normalized_price,
                component_scores=component_scores,
                unknown_factors=unknown_factors,
                explanations=explanations,
            )
        )

    groups: dict[str, list[_DraftRanking]] = {}
    for draft in drafts:
        if draft.rankable:
            groups.setdefault(draft.comparison_group, []).append(draft)

    for group in groups.values():
        prices = [
            draft.normalized_unit_price.amount
            for draft in group
            if draft.normalized_unit_price is not None
        ]
        minimum_price = min(prices)
        for draft in group:
            assert draft.normalized_unit_price is not None
            if len(group) == 1:
                price_points = 12
                draft.explanations.append(
                    "تنها پیشنهاد قابل‌رتبه‌بندی گروه است؛ امتیاز قیمت خنثی محاسبه شد."
                )
            else:
                price_points = _rounded_points(
                    minimum_price / draft.normalized_unit_price.amount * Decimal("25")
                )
                draft.explanations.append(
                    f"امتیاز قیمت نسبت به کمترین قیمت قابل‌مقایسه {price_points}/25 است."
                )
            draft.component_scores["price_competitiveness"] = price_points

        ordered = sorted(
            group,
            key=lambda item: (
                -sum(item.component_scores.values()),
                item.normalized_unit_price.amount if item.normalized_unit_price else Decimal("0"),
                item.observation.observation_id,
            ),
        )
        previous_key: tuple[int, Decimal] | None = None
        current_rank = 0
        for position, draft in enumerate(ordered, start=1):
            assert draft.normalized_unit_price is not None
            ranking_key = (sum(draft.component_scores.values()), draft.normalized_unit_price.amount)
            if ranking_key != previous_key:
                current_rank = position
                previous_key = ranking_key
            draft.rank = current_rank

    results: list[SupplierOfferRanking] = []
    for draft in drafts:
        draft.total_score = sum(draft.component_scores.values())
        if not draft.rankable:
            draft.explanations.append("پیشنهاد به‌دلیل داده ناکافی یا عدم انطباق رتبه نگرفت.")
        results.append(
            SupplierOfferRanking(
                observation_id=draft.observation.observation_id,
                supplier_name=draft.observation.supplier_name,
                comparison_group=draft.comparison_group,
                rank=draft.rank,
                eligible_for_quantity=draft.eligible,
                rankable=draft.rankable,
                normalized_unit_price=draft.normalized_unit_price,
                total_score=draft.total_score,
                component_scores=dict(draft.component_scores),
                unknown_factors=tuple(sorted(set(draft.unknown_factors))),
                explanation_fa=tuple(draft.explanations),
                policy_version=SUPPLIER_RANKING_POLICY_VERSION,
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.comparison_group,
                item.rank is None,
                item.rank or 0,
                item.observation_id,
            ),
        )
    )
