from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trade_agent.domain.errors import PublicInputError

RECORDED_CORE_TERM_FIELDS = (
    "supplier_identity",
    "minimum_order_quantity",
    "product_specification",
    "incoterm",
    "incoterm_named_place",
    "incoterm_version",
    "payment_terms",
    "payment_method",
    "quote_valid_until",
    "lead_time_days",
)
UNCAPTURED_COMMERCIAL_TERM_FIELDS = (
    "supplier_capacity",
    "certifications",
    "warranty",
    "inspection_terms",
)


@dataclass(frozen=True, slots=True)
class OfferTermsPoint:
    observation_id: str
    supplier_name: str | None
    minimum_order_quantity: int | None
    product_variant: str | None
    product_attributes: dict[str, str]
    incoterm: str | None
    incoterm_named_place: str | None
    incoterm_version: str | None
    payment_terms: str | None
    payment_method: str | None
    quote_valid_until: datetime | None
    lead_time_days: int | None
    rankable: bool
    ranking_unknown_factors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OfferTermsCoverage:
    observation_id: str
    supplier_name: str | None
    declared_fields: tuple[str, ...]
    missing_recorded_fields: tuple[str, ...]
    declared_recorded_field_count: int
    rankable: bool
    ranking_unknown_factors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OfferTermsCoverageSummary:
    status: str
    recorded_core_term_fields: tuple[str, ...]
    offers: tuple[OfferTermsCoverage, ...]
    uncaptured_commercial_term_fields: tuple[str, ...]
    limitations: tuple[str, ...]


def summarize_offer_terms_coverage(
    points: tuple[OfferTermsPoint, ...],
) -> OfferTermsCoverageSummary:
    observation_ids = [point.observation_id for point in points]
    if len(observation_ids) != len(set(observation_ids)):
        raise PublicInputError("offer-terms observation IDs must be unique")

    offers: list[OfferTermsCoverage] = []
    for point in sorted(points, key=lambda item: item.observation_id):
        declarations = {
            "supplier_identity": bool(point.supplier_name and point.supplier_name.strip()),
            "minimum_order_quantity": point.minimum_order_quantity is not None,
            "product_specification": bool(
                (point.product_variant and point.product_variant.strip())
                or point.product_attributes
            ),
            "incoterm": bool(point.incoterm and point.incoterm.strip()),
            "incoterm_named_place": bool(
                point.incoterm_named_place and point.incoterm_named_place.strip()
            ),
            "incoterm_version": bool(
                point.incoterm_version and point.incoterm_version.strip()
            ),
            "payment_terms": bool(point.payment_terms and point.payment_terms.strip()),
            "payment_method": bool(point.payment_method and point.payment_method.strip()),
            "quote_valid_until": point.quote_valid_until is not None,
            "lead_time_days": point.lead_time_days is not None,
        }
        declared = tuple(
            field for field in RECORDED_CORE_TERM_FIELDS if declarations[field]
        )
        missing = tuple(
            field for field in RECORDED_CORE_TERM_FIELDS if not declarations[field]
        )
        offers.append(
            OfferTermsCoverage(
                observation_id=point.observation_id,
                supplier_name=(
                    point.supplier_name.strip()
                    if point.supplier_name and point.supplier_name.strip()
                    else None
                ),
                declared_fields=declared,
                missing_recorded_fields=missing,
                declared_recorded_field_count=len(declared),
                rankable=point.rankable,
                ranking_unknown_factors=tuple(sorted(set(point.ranking_unknown_factors))),
            )
        )

    if not offers:
        status = "NO_OFFERS"
    elif any(offer.missing_recorded_fields for offer in offers):
        status = "RECORDED_CORE_TERM_GAPS"
    else:
        status = "RECORDED_CORE_TERMS_PRESENT"
    return OfferTermsCoverageSummary(
        status=status,
        recorded_core_term_fields=RECORDED_CORE_TERM_FIELDS,
        offers=tuple(offers),
        uncaptured_commercial_term_fields=UNCAPTURED_COMMERCIAL_TERM_FIELDS,
        limitations=(
            "field presence does not verify supplier identity or negotiated terms",
            "uncaptured fields are schema gaps and are not assumed absent or inapplicable",
            "no completeness percentage is calculated and rankability is a separate policy",
            "payment and timing field presence is not proof that terms remain current "
            "or acceptable",
            "capacity, certification, warranty, and inspection terms need evidence",
        ),
    )
