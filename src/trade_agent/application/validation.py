from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from statistics import median
from typing import Any

from trade_agent.application.evidence_freshness import (
    DEFAULT_MAX_EVIDENCE_AGE,
    MAX_FUTURE_CLOCK_SKEW,
)
from trade_agent.application.incoterms import INCOTERMS_2020_CODES
from trade_agent.domain.models import (
    Confidence,
    Evidence,
    EvidenceClass,
    PriceObservation,
    ProductMatch,
    ProductMatchClass,
    ResearchCase,
    SupplierOfferRanking,
)

VALIDATION_POLICY_VERSION = "2026-09-01.3"
OUTLIER_FACTOR = Decimal("3")
KNOWN_INCOTERMS = frozenset(INCOTERMS_2020_CODES)


class ValidationSeverity(StrEnum):
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationDisposition(StrEnum):
    PASSED = "PASSED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    severity: ValidationSeverity
    message_fa: str
    subject_type: str
    subject_id: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    policy_version: str
    evaluated_at: datetime
    disposition: ValidationDisposition
    confidence_score: int
    confidence_label: Confidence
    issues: tuple[ValidationIssue, ...]


def _normal(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _observation_fingerprint(observation: PriceObservation) -> tuple[object, ...]:
    return (
        _normal(observation.product_name),
        _normal(observation.product_variant),
        _normal(observation.supplier_name),
        observation.unit_price.amount.normalize(),
        observation.unit_price.currency,
        observation.quantity,
        observation.unit,
        observation.minimum_order_quantity,
        _normal(observation.incoterm),
        _normal(observation.incoterm_named_place),
        _normal(observation.incoterm_version),
        _normal(observation.payment_terms),
        _normal(observation.payment_method),
        observation.quote_valid_until,
        observation.lead_time_days,
        observation.market_layer.casefold(),
        observation.evidence.source_url,
        observation.evidence.retrieved_at,
        observation.evidence.raw_value,
    )


def _evidence_issues(
    evidence: Evidence,
    *,
    subject_type: str,
    subject_id: str,
    evaluated_at: datetime,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    age = evaluated_at - evidence.retrieved_at.astimezone(UTC)
    if age > DEFAULT_MAX_EVIDENCE_AGE:
        issues.append(
            ValidationIssue(
                code="STALE_EVIDENCE",
                severity=ValidationSeverity.WARNING,
                message_fa="تاریخ بازیابی این شاهد بیش از ۳۰ روز با زمان ارزیابی فاصله دارد.",
                subject_type=subject_type,
                subject_id=subject_id,
                details={"age_days": age.days, "max_age_days": DEFAULT_MAX_EVIDENCE_AGE.days},
            )
        )
    if age < -MAX_FUTURE_CLOCK_SKEW:
        issues.append(
            ValidationIssue(
                code="FUTURE_DATED_EVIDENCE",
                severity=ValidationSeverity.ERROR,
                message_fa="زمان بازیابی شاهد در آینده ثبت شده و باید بررسی انسانی شود.",
                subject_type=subject_type,
                subject_id=subject_id,
                details={"retrieved_at": evidence.retrieved_at.isoformat()},
            )
        )
    if evidence.confidence in {Confidence.LOW, Confidence.UNKNOWN}:
        issues.append(
            ValidationIssue(
                code="LOW_EVIDENCE_CONFIDENCE",
                severity=ValidationSeverity.WARNING,
                message_fa="سطح اعتماد شاهد پایین یا نامشخص است.",
                subject_type=subject_type,
                subject_id=subject_id,
                details={"confidence": evidence.confidence.value},
            )
        )
    if evidence.classification in {EvidenceClass.ASSUMPTION, EvidenceClass.AI_INFERENCE}:
        issues.append(
            ValidationIssue(
                code="NON_FACT_EVIDENCE",
                severity=ValidationSeverity.WARNING,
                message_fa="این ورودی شاهد قطعی نیست و پیش از تصمیم خرید باید تأیید شود.",
                subject_type=subject_type,
                subject_id=subject_id,
                details={"classification": evidence.classification.value},
            )
        )
    return issues


def _confidence(issues: list[ValidationIssue]) -> tuple[int, Confidence]:
    penalty = sum(30 if issue.severity is ValidationSeverity.ERROR else 10 for issue in issues)
    score = max(0, 100 - penalty)
    if score >= 80:
        return score, Confidence.HIGH
    if score >= 60:
        return score, Confidence.MEDIUM
    if score > 0:
        return score, Confidence.LOW
    return score, Confidence.UNKNOWN


def validate_research_case(
    case: ResearchCase, *, evaluated_at: datetime | None = None
) -> tuple[ResearchCase, ValidationResult]:
    evaluation_time = evaluated_at or datetime.now(UTC)
    if evaluation_time.tzinfo is None:
        raise ValueError("validation evaluated_at must be timezone-aware")
    evaluation_time = evaluation_time.astimezone(UTC)
    issues: list[ValidationIssue] = []

    unique_observations: list[PriceObservation] = []
    seen_fingerprints: dict[tuple[object, ...], str] = {}
    for observation in case.observations:
        fingerprint = _observation_fingerprint(observation)
        duplicate_of = seen_fingerprints.get(fingerprint)
        if duplicate_of is not None:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_PRICE_OBSERVATION",
                    severity=ValidationSeverity.WARNING,
                    message_fa="مشاهده قیمت تکراری از محاسبه و ذخیره‌سازی حذف شد.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=observation.observation_id,
                    details={"duplicate_of": duplicate_of},
                )
            )
            continue
        seen_fingerprints[fingerprint] = observation.observation_id
        unique_observations.append(observation)

    retained_observation_ids = {
        observation.observation_id for observation in unique_observations
    }
    retained_identity_claims = tuple(
        claim
        for claim in case.supplier_identity_claims
        if claim.observation_id in retained_observation_ids
    )
    for claim in case.supplier_identity_claims:
        if claim.observation_id not in retained_observation_ids:
            issues.append(
                ValidationIssue(
                    code="IDENTITY_CLAIM_FOR_EXCLUDED_OBSERVATION",
                    severity=ValidationSeverity.ERROR,
                    message_fa=(
                        "ادعای هویت به مشاهده قیمت تکراری یا حذف‌شده متصل بود و "
                        "برای جلوگیری از انتساب ضمنی کنار گذاشته شد."
                    ),
                    subject_type="SUPPLIER_IDENTITY_CLAIM",
                    subject_id=claim.claim_id,
                    details={"observation_id": claim.observation_id},
                )
            )
    clean_case = replace(
        case,
        observations=tuple(unique_observations),
        supplier_identity_claims=retained_identity_claims,
    )
    if not clean_case.observations:
        issues.append(
            ValidationIssue(
                code="NO_PRICE_OBSERVATIONS",
                severity=ValidationSeverity.ERROR,
                message_fa="هیچ مشاهده قیمت یکتایی برای این پرونده وجود ندارد.",
                subject_type="RESEARCH_CASE",
                subject_id=case.case_id,
            )
        )

    price_units = {observation.unit for observation in clean_case.observations}
    if len(price_units) > 1:
        issues.append(
            ValidationIssue(
                code="MIXED_PRICE_UNITS",
                severity=ValidationSeverity.WARNING,
                message_fa="واحد مشاهدات قیمت یکسان نیست و مقایسه مستقیم نیازمند نرمال‌سازی است.",
                subject_type="RESEARCH_CASE",
                subject_id=case.case_id,
                details={"units": sorted(price_units)},
            )
        )

    eligible_count = 0
    grouped_prices: dict[tuple[str, str], list[PriceObservation]] = {}
    for observation in clean_case.observations:
        if observation.unit_price.amount == 0:
            issues.append(
                ValidationIssue(
                    code="ZERO_PRICE",
                    severity=ValidationSeverity.ERROR,
                    message_fa="قیمت صفر برای تصمیم بازرگانی معتبر نیست و باید تأیید شود.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=observation.observation_id,
                )
            )
        if observation.incoterm and observation.incoterm.upper() not in KNOWN_INCOTERMS:
            issues.append(
                ValidationIssue(
                    code="UNKNOWN_INCOTERM",
                    severity=ValidationSeverity.WARNING,
                    message_fa="این Incoterm در فهرست استاندارد پشتیبانی‌شده شناخته نشد.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=observation.observation_id,
                    details={"incoterm": observation.incoterm},
                )
            )
        incoterm_fields_declared = any(
            (
                observation.incoterm,
                observation.incoterm_named_place,
                observation.incoterm_version,
            )
        )
        if incoterm_fields_declared:
            missing_incoterm_fields = tuple(
                field_name
                for field_name, value in (
                    ("incoterm", observation.incoterm),
                    ("incoterm_named_place", observation.incoterm_named_place),
                    ("incoterm_version", observation.incoterm_version),
                )
                if value is None
            )
            if missing_incoterm_fields:
                issues.append(
                    ValidationIssue(
                        code="INCOMPLETE_INCOTERM_TERMS",
                        severity=ValidationSeverity.WARNING,
                        message_fa=(
                            "کد، محل نام‌برده‌شده و نسخه Incoterm باید کنار هم "
                            "ثبت شوند."
                        ),
                        subject_type="PRICE_OBSERVATION",
                        subject_id=observation.observation_id,
                        details={"missing_fields": list(missing_incoterm_fields)},
                    )
                )
        if (
            observation.quote_valid_until is not None
            and observation.quote_valid_until < evaluation_time
        ):
            issues.append(
                ValidationIssue(
                    code="QUOTE_VALIDITY_EXPIRED",
                    severity=ValidationSeverity.WARNING,
                    message_fa="مهلت اعتبار اعلام‌شده برای این پیشنهاد گذشته است.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=observation.observation_id,
                    details={
                        "quote_valid_until": observation.quote_valid_until.isoformat(),
                        "evaluated_at": evaluation_time.isoformat(),
                    },
                )
            )
        if (
            observation.minimum_order_quantity is None
            or case.quantity >= observation.minimum_order_quantity
        ):
            eligible_count += 1
        grouped_prices.setdefault(
            (observation.unit_price.currency, observation.unit), []
        ).append(observation)
        issues.extend(
            _evidence_issues(
                observation.evidence,
                subject_type="PRICE_OBSERVATION",
                subject_id=observation.observation_id,
                evaluated_at=evaluation_time,
            )
        )

    for claim in clean_case.supplier_identity_claims:
        issues.extend(
            _evidence_issues(
                claim.evidence,
                subject_type="SUPPLIER_IDENTITY_CLAIM",
                subject_id=claim.claim_id,
                evaluated_at=evaluation_time,
            )
        )
        issues.append(
            ValidationIssue(
                code="SUPPLIER_IDENTITY_CLAIM_REQUIRES_REVIEW",
                severity=ValidationSeverity.WARNING,
                message_fa=(
                    "این رکورد فقط ادعای منبع درباره هویت حقوقی را نگه می‌دارد و "
                    "تا بازبینی مستقل، هویت تأمین‌کننده را تأیید نمی‌کند."
                ),
                subject_type="SUPPLIER_IDENTITY_CLAIM",
                subject_id=claim.claim_id,
                details={"observation_id": claim.observation_id},
            )
        )

    if clean_case.observations and eligible_count == 0:
        issues.append(
            ValidationIssue(
                code="NO_QUANTITY_ELIGIBLE_PRICE",
                severity=ValidationSeverity.ERROR,
                message_fa="هیچ قیمت ثبت‌شده‌ای با تعداد درخواستی و حداقل سفارش سازگار نیست.",
                subject_type="RESEARCH_CASE",
                subject_id=case.case_id,
                details={"requested_quantity": case.quantity},
            )
        )

    for (currency, unit), observations in grouped_prices.items():
        positive = [item for item in observations if item.unit_price.amount > 0]
        if len(positive) < 3:
            continue
        midpoint = Decimal(str(median([item.unit_price.amount for item in positive])))
        for observation in positive:
            amount = observation.unit_price.amount
            if amount > midpoint * OUTLIER_FACTOR or amount * OUTLIER_FACTOR < midpoint:
                issues.append(
                    ValidationIssue(
                        code="PRICE_OUTLIER",
                        severity=ValidationSeverity.WARNING,
                        message_fa="این قیمت بیش از آستانه سه‌برابری از میانه گروه فاصله دارد.",
                        subject_type="PRICE_OBSERVATION",
                        subject_id=observation.observation_id,
                        details={
                            "amount": str(amount),
                            "median": str(midpoint),
                            "currency": currency,
                            "unit": unit,
                        },
                    )
                )

    backed_prices = {
        (observation.unit_price.amount, observation.unit_price.currency)
        for observation in clean_case.observations
        if observation.minimum_order_quantity is None
        or case.quantity >= observation.minimum_order_quantity
    }
    for scenario in case.scenarios:
        if scenario.quantity != case.quantity:
            issues.append(
                ValidationIssue(
                    code="SCENARIO_QUANTITY_MISMATCH",
                    severity=ValidationSeverity.ERROR,
                    message_fa="تعداد سناریو با تعداد پرونده یکسان نیست.",
                    subject_type="SCENARIO",
                    subject_id=scenario.name.value,
                    details={
                        "case_quantity": case.quantity,
                        "scenario_quantity": scenario.quantity,
                    },
                )
            )
        purchase_key = (scenario.purchase_unit_price.amount, scenario.purchase_unit_price.currency)
        if purchase_key not in backed_prices:
            issues.append(
                ValidationIssue(
                    code="UNBACKED_PURCHASE_PRICE",
                    severity=ValidationSeverity.WARNING,
                    message_fa="قیمت خرید سناریو مستقیماً با یک مشاهده واجد شرایط تطبیق ندارد.",
                    subject_type="SCENARIO",
                    subject_id=scenario.name.value,
                    details={
                        "amount": str(scenario.purchase_unit_price.amount),
                        "currency": scenario.purchase_unit_price.currency,
                    },
                )
            )
        assumed_costs = [
            cost.code
            for cost in scenario.costs
            if cost.evidence_class in {EvidenceClass.ASSUMPTION, EvidenceClass.AI_INFERENCE}
        ]
        if assumed_costs:
            issues.append(
                ValidationIssue(
                    code="ASSUMED_COST_COMPONENTS",
                    severity=ValidationSeverity.WARNING,
                    message_fa="برخی اجزای هزینه این سناریو فرضی یا استنباطی‌اند.",
                    subject_type="SCENARIO",
                    subject_id=scenario.name.value,
                    details={"component_codes": assumed_costs},
                )
            )

    unique_rates: dict[
        tuple[str, str, Decimal, str, datetime | None, Evidence],
        set[str],
    ] = {}
    for scenario in case.scenarios:
        for rate in scenario.fx_rates:
            key = (
                rate.base_currency,
                rate.quote_currency,
                rate.rate,
                rate.rate_type,
                rate.effective_at,
                rate.evidence,
            )
            unique_rates.setdefault(key, set()).add(scenario.name.value)
    for (
        base,
        quote,
        value,
        rate_type,
        effective_at,
        evidence,
    ), scenario_names in unique_rates.items():
        scenarios = ",".join(sorted(scenario_names))
        subject_id = (
            f"{scenarios}:{base}/{quote}:{value}:{rate_type}:"
            f"{effective_at or 'unspecified'}"
        )
        issues.extend(
            _evidence_issues(
                evidence,
                subject_type="FX_RATE",
                subject_id=subject_id,
                evaluated_at=evaluation_time,
            )
        )

    if case.unknowns:
        issues.append(
            ValidationIssue(
                code="DECLARED_UNKNOWNS",
                severity=ValidationSeverity.WARNING,
                message_fa="پرونده دارای مجهولات اعلام‌شده است که باید پیش از خرید بسته شوند.",
                subject_type="RESEARCH_CASE",
                subject_id=case.case_id,
                details={"count": len(case.unknowns)},
            )
        )

    score, label = _confidence(issues)
    if any(issue.severity is ValidationSeverity.ERROR for issue in issues):
        disposition = ValidationDisposition.NEEDS_HUMAN_REVIEW
    elif issues:
        disposition = ValidationDisposition.NEEDS_VERIFICATION
    else:
        disposition = ValidationDisposition.PASSED
    return clean_case, ValidationResult(
        policy_version=VALIDATION_POLICY_VERSION,
        evaluated_at=evaluation_time,
        disposition=disposition,
        confidence_score=score,
        confidence_label=label,
        issues=tuple(issues),
    )


def validate_product_matches(
    validation: ValidationResult, matches: tuple[ProductMatch, ...]
) -> ValidationResult:
    additions: list[ValidationIssue] = []
    for match in matches:
        if match.conflicting_attributes:
            additions.append(
                ValidationIssue(
                    code="PRODUCT_ATTRIBUTE_CONFLICT",
                    severity=ValidationSeverity.ERROR,
                    message_fa="ویژگی‌های محصول مشاهده‌شده با نیاز پرونده تعارض دارد.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=match.observation_id,
                    details={"attributes": list(match.conflicting_attributes)},
                )
            )
        elif match.classification is ProductMatchClass.EXACT_PRODUCT and match.missing_attributes:
            additions.append(
                ValidationIssue(
                    code="UNVERIFIED_PRODUCT_VARIANT",
                    severity=ValidationSeverity.WARNING,
                    message_fa="محصول دقیق است اما همه ویژگی‌های واریانت تأیید نشده‌اند.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=match.observation_id,
                    details={"missing_attributes": list(match.missing_attributes)},
                )
            )

        if match.classification is ProductMatchClass.COMPARABLE:
            additions.append(
                ValidationIssue(
                    code="COMPARABLE_PRODUCT_PRICE",
                    severity=ValidationSeverity.WARNING,
                    message_fa="قیمت مربوط به محصول قابل‌مقایسه است، نه تطبیق دقیق.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=match.observation_id,
                    details={"match_score": match.score},
                )
            )
        elif match.classification is ProductMatchClass.SIMILAR:
            additions.append(
                ValidationIssue(
                    code="SIMILAR_PRODUCT_PRICE",
                    severity=ValidationSeverity.WARNING,
                    message_fa="قیمت مربوط به محصول مشابه است و نباید معادل دقیق تلقی شود.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=match.observation_id,
                    details={"match_score": match.score},
                )
            )
        elif match.classification is ProductMatchClass.SUBSTITUTE:
            additions.append(
                ValidationIssue(
                    code="SUBSTITUTE_PRODUCT_PRICE",
                    severity=ValidationSeverity.ERROR,
                    message_fa=(
                        "قیمت مربوط به محصول جایگزین است و استفاده مستقیم "
                        "نیازمند بررسی انسانی است."
                    ),
                    subject_type="PRICE_OBSERVATION",
                    subject_id=match.observation_id,
                    details={"match_score": match.score},
                )
            )

    issues = [*validation.issues, *additions]
    score, label = _confidence(issues)
    if any(issue.severity is ValidationSeverity.ERROR for issue in issues):
        disposition = ValidationDisposition.NEEDS_HUMAN_REVIEW
    elif issues:
        disposition = ValidationDisposition.NEEDS_VERIFICATION
    else:
        disposition = ValidationDisposition.PASSED
    return replace(
        validation,
        disposition=disposition,
        confidence_score=score,
        confidence_label=label,
        issues=tuple(issues),
    )


def validate_supplier_rankings(
    validation: ValidationResult,
    rankings: tuple[SupplierOfferRanking, ...],
) -> ValidationResult:
    additions: list[ValidationIssue] = []
    reviewed_suppliers: set[str] = set()
    rankable_by_group: dict[str, int] = {}
    for ranking in rankings:
        if ranking.rankable:
            rankable_by_group[ranking.comparison_group] = (
                rankable_by_group.get(ranking.comparison_group, 0) + 1
            )
        if not ranking.supplier_name:
            additions.append(
                ValidationIssue(
                    code="MISSING_SUPPLIER_IDENTITY",
                    severity=ValidationSeverity.ERROR,
                    message_fa="پیشنهاد بدون هویت تأمین‌کننده قابل اقدام یا رتبه‌بندی نیست.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=ranking.observation_id,
                )
            )
        elif ranking.supplier_name not in reviewed_suppliers:
            reviewed_suppliers.add(ranking.supplier_name)
            additions.append(
                ValidationIssue(
                    code="SUPPLIER_DUE_DILIGENCE_REQUIRED",
                    severity=ValidationSeverity.WARNING,
                    message_fa=(
                        "اعتبار، مجوزها، توان تحویل و شرایط پرداخت تأمین‌کننده "
                        "هنوز راستی‌آزمایی نشده است."
                    ),
                    subject_type="SUPPLIER",
                    subject_id=ranking.supplier_name,
                )
            )
        if not ranking.eligible_for_quantity:
            additions.append(
                ValidationIssue(
                    code="OFFER_BELOW_MINIMUM_ORDER",
                    severity=ValidationSeverity.WARNING,
                    message_fa="تعداد درخواستی به حداقل سفارش این پیشنهاد نمی‌رسد.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=ranking.observation_id,
                )
            )
        if ranking.normalized_unit_price is None:
            additions.append(
                ValidationIssue(
                    code="UNCONVERTIBLE_OFFER_PRICE",
                    severity=ValidationSeverity.ERROR,
                    message_fa="قیمت پیشنهاد به ارز مقایسه تبدیل نشد و قابل رتبه‌بندی نیست.",
                    subject_type="PRICE_OBSERVATION",
                    subject_id=ranking.observation_id,
                )
            )

    comparison_groups = {ranking.comparison_group for ranking in rankings}
    for group in sorted(comparison_groups):
        if rankable_by_group.get(group, 0) < 2:
            additions.append(
                ValidationIssue(
                    code="INSUFFICIENT_SUPPLIER_COMPARISON",
                    severity=ValidationSeverity.WARNING,
                    message_fa="برای این گروه کمتر از دو پیشنهاد قابل‌رتبه‌بندی وجود دارد.",
                    subject_type="SUPPLIER_COMPARISON_GROUP",
                    subject_id=group,
                    details={"rankable_offer_count": rankable_by_group.get(group, 0)},
                )
            )

    issues = [*validation.issues, *additions]
    score, label = _confidence(issues)
    if any(issue.severity is ValidationSeverity.ERROR for issue in issues):
        disposition = ValidationDisposition.NEEDS_HUMAN_REVIEW
    elif issues:
        disposition = ValidationDisposition.NEEDS_VERIFICATION
    else:
        disposition = ValidationDisposition.PASSED
    return replace(
        validation,
        disposition=disposition,
        confidence_score=score,
        confidence_label=label,
        issues=tuple(issues),
    )
