from __future__ import annotations

import html
import re
from urllib.parse import quote

from trade_agent.application.quantity import (
    QuantityPricePoint,
    analyze_quantity_points,
    quantity_product_key,
)
from trade_agent.application.research import ResearchResult
from trade_agent.application.sensitivity import analyze_scenario_sensitivity, cost_points

_MARKDOWN_SPECIAL = frozenset("\\`*_{}[]()#!|")
_BACKTICK_RUN = re.compile(r"`+")


def _single_line(value: object) -> str:
    return " ".join(str(value).splitlines())


def _text(value: object) -> str:
    escaped_html = html.escape(_single_line(value), quote=False)
    return "".join(
        f"\\{character}" if character in _MARKDOWN_SPECIAL else character
        for character in escaped_html
    )


def _code(value: object) -> str:
    content = html.escape(_single_line(value), quote=False)
    longest_run = max((len(match.group()) for match in _BACKTICK_RUN.finditer(content)), default=0)
    fence = "`" * (longest_run + 1)
    padding = " " if content.startswith("`") or content.endswith("`") else ""
    return f"{fence}{padding}{content}{padding}{fence}"


def _link_target(url: str) -> str:
    return quote(_single_line(url).strip(), safe=":/?#@!$&'+,;=%~")


def render_markdown(result: ResearchResult) -> str:
    case = result.case
    validation = result.validation
    lines = [
        f"# گزارش تصمیم بازرگانی — {_text(case.product_name)}",
        "",
        f"- شناسه پرونده: {_code(case.case_id)}",
        f"- تعداد: {case.quantity:,}",
        f"- مقصد: {_text(case.destination)}",
        f"- تعداد مشاهدات قیمت: {len(case.observations)}",
        f"- وضعیت اعتبارسنجی: {_code(validation.disposition.value)}",
        f"- امتیاز اعتماد توضیح‌پذیر: {validation.confidence_score}/100 "
        f"({_code(validation.confidence_label.value)})",
        "",
        "## کیفیت داده و نیاز به بازبینی",
        "",
        f"- نسخه سیاست اعتبارسنجی: {_code(validation.policy_version)}",
        f"- زمان ارزیابی: {validation.evaluated_at.isoformat()}",
        "- روش امتیازدهی: شروع از ۱۰۰؛ هر هشدار ۱۰- و هر خطا ۳۰- (حداقل صفر).",
    ]
    if validation.issues:
        lines.extend(
            f"- **{_text(issue.severity.value)} / {_text(issue.code)}** "
            f"({_code(f'{issue.subject_type}:{issue.subject_id or "-"}')}) — "
            f"{_text(issue.message_fa)}"
            for issue in validation.issues
        )
    else:
        lines.append("- خطای کیفیت داده شناسایی نشد.")

    lines.extend(
        [
        "",
        "## خلاصه سناریوها",
        "",
        "| سناریو | کل بهای تمام‌شده | بهای هر واحد | ارز |",
        "|---|---:|---:|---|",
        ]
    )
    for scenario in result.scenarios:
        lines.append(
            f"| {scenario.name.value} | {scenario.total.amount:,.2f} | "
            f"{scenario.per_unit.amount:,.2f} | {scenario.target_currency} |"
        )

    sensitivity = analyze_scenario_sensitivity(cost_points(result.scenarios))
    lines.extend(["", "## حساسیت سناریوها", ""])
    if sensitivity.status == "COMPARABLE":
        lines.extend(
            [
                f"- مبنا: {sensitivity.base_per_unit:,.2f} "
                f"{sensitivity.target_currency} برای {sensitivity.quantity:,} واحد",
                f"- فاصله OPTIMISTIC با BASE: "
                f"{sensitivity.optimistic_delta_from_base:,.2f} "
                f"({sensitivity.optimistic_delta_percent:,.2f}%)",
                f"- فاصله CONSERVATIVE با BASE: "
                f"{sensitivity.conservative_delta_from_base:,.2f} "
                f"({sensitivity.conservative_delta_percent:,.2f}%)",
                f"- دامنه کل بهای هر واحد: {sensitivity.range_per_unit:,.2f} "
                f"({sensitivity.range_percent_of_base:,.2f}% از BASE)",
            ]
        )
    else:
        lines.append(f"- وضعیت: {_code(sensitivity.status)}")
    lines.extend(f"- محدودیت: {_text(item)}" for item in sensitivity.limitations)

    lines.extend(["", "## نرخ‌های ارز سناریوها", ""])
    for scenario_input in result.case.scenarios:
        if not scenario_input.fx_rates:
            lines.append(f"- {_code(scenario_input.name.value)}: نرخ تبدیل ثبت نشده است.")
            continue
        for rate in scenario_input.fx_rates:
            effective_at = rate.effective_at.isoformat() if rate.effective_at else "نامشخص"
            lines.append(
                f"- {_code(scenario_input.name.value)}: 1 {_code(rate.base_currency)} = "
                f"{rate.rate} {_code(rate.quote_currency)}؛ نوع {_code(rate.rate_type)}؛ "
                f"زمان مؤثر {_code(effective_at)}؛ کلاس "
                f"{_code(rate.evidence.classification.value)}؛ "
                f"[{_text(rate.evidence.source_name)}]"
                f"({_link_target(rate.evidence.source_url)})"
            )

    lines.extend(["", "## جزئیات محاسبات", ""])
    for scenario in result.scenarios:
        lines.extend([f"### {_text(scenario.name.value)}", ""])
        for component in scenario.components:
            lines.append(
                f"- {_text(component.label_fa)}: {component.amount.amount:,.2f} "
                f"{component.amount.currency} — {_code(component.evidence_class.value)}"
            )
        lines.append("")

    lines.extend(["## شواهد قیمت", ""])
    for observation in case.observations:
        lines.append(
            f"- [{_text(observation.evidence.source_name)}]"
            f"({_link_target(observation.evidence.source_url)}): "
            f"{observation.unit_price.amount} {observation.unit_price.currency}، "
            f"واحد {_code(observation.unit)}، "
            f"کلاس {_code(observation.evidence.classification.value)}، "
            f"اعتماد {_code(observation.evidence.confidence.value)}"
        )

    lines.extend(["", "## تطبیق محصول", ""])
    if case.product_attributes:
        requested_attributes = "، ".join(
            _code(f"{key}={value}") for key, value in sorted(case.product_attributes.items())
        )
        lines.append(f"- ویژگی‌های مرجع پرونده: {requested_attributes}")
    for match in result.product_matches:
        lines.append(
            f"- مشاهده {_code(match.observation_id)}: {_code(match.classification.value)}، "
            f"امتیاز {match.score}/100، شباهت نام {match.name_similarity:.2f}"
        )
        lines.extend(f"  - {_text(reason)}" for reason in match.explanation_fa)
    if not result.product_matches:
        lines.append("- مشاهده‌ای برای تطبیق وجود ندارد.")

    lines.extend(["", "## رتبه‌بندی پیشنهادهای تأمین‌کننده", ""])
    lines.append(
        "> این رتبه‌بندی کیفیت پیشنهاد ثبت‌شده را مقایسه می‌کند و به‌تنهایی تأیید اعتبار "
        "تأمین‌کننده نیست."
    )
    for ranking in result.supplier_rankings:
        rank_label = str(ranking.rank) if ranking.rank is not None else "بدون رتبه"
        normalized = (
            f"{ranking.normalized_unit_price.amount:,.2f} "
            f"{ranking.normalized_unit_price.currency}"
            if ranking.normalized_unit_price
            else "غیرقابل تبدیل"
        )
        lines.append(
            f"- {_text(ranking.supplier_name or 'تأمین‌کننده نامشخص')} — "
            f"رتبه {rank_label} در {_code(ranking.comparison_group)}، "
            f"امتیاز {ranking.total_score}/100، "
            f"قیمت واحد نرمال‌شده {normalized}"
        )
        component_text = "، ".join(
            f"{key}={value}" for key, value in sorted(ranking.component_scores.items())
        )
        lines.append(f"  - اجزای امتیاز: {_text(component_text)}")
        if ranking.unknown_factors:
            lines.append(
                f"  - عوامل نامشخص: {_text(', '.join(ranking.unknown_factors))}"
            )
        lines.extend(f"  - {_text(reason)}" for reason in ranking.explanation_fa)
    if not result.supplier_rankings:
        lines.append("- پیشنهادی برای رتبه‌بندی وجود ندارد.")

    ranking_by_observation = {
        ranking.observation_id: ranking for ranking in result.supplier_rankings
    }
    quantity_points: list[QuantityPricePoint] = []
    for observation in case.observations:
        ranking = ranking_by_observation[observation.observation_id]
        normalized_price = ranking.normalized_unit_price
        quantity_points.append(
            QuantityPricePoint(
                observation_id=observation.observation_id,
                supplier_name=observation.supplier_name,
                product_name=observation.product_name,
                product_variant=observation.product_variant,
                product_group_key=quantity_product_key(
                    observation.product_name,
                    observation.product_variant,
                    observation.product_attributes,
                ),
                comparison_group=ranking.comparison_group,
                quoted_quantity=observation.quantity,
                minimum_order_quantity=observation.minimum_order_quantity,
                eligible_for_requested_quantity=ranking.eligible_for_quantity,
                original_amount=observation.unit_price.amount,
                original_currency=observation.unit_price.currency,
                normalized_amount=(normalized_price.amount if normalized_price else None),
                normalized_currency=(
                    normalized_price.currency if normalized_price else None
                ),
                source_name=observation.evidence.source_name,
                source_url=observation.evidence.source_url,
            )
        )
    quantity_analysis = analyze_quantity_points(case.quantity, tuple(quantity_points))
    lines.extend(["", "## تحلیل تعداد", ""])
    lines.append(f"- وضعیت: {_code(quantity_analysis.status)}")
    lines.append(f"- تعداد درخواستی: {quantity_analysis.requested_quantity:,}")
    for offer_series in quantity_analysis.series:
        supplier = offer_series.supplier_name or "تأمین‌کننده نامشخص"
        variant = offer_series.product_variant or "نامشخص"
        lines.append(
            f"- {_text(supplier)} — محصول {_text(offer_series.product_name)}، "
            f"variant {_code(variant)}، گروه {_code(offer_series.comparison_group)}"
        )
        for point in offer_series.points:
            normalized = (
                f"{point.normalized_amount} "
                f"{_code(point.normalized_currency or 'UNKNOWN')}"
                if point.normalized_amount is not None
                else "غیرقابل‌مقایسه"
            )
            change = (
                f"؛ تغییر نسبت به نقطه قبل "
                f"{point.normalized_change_from_previous_percent}%"
                if point.normalized_change_from_previous_percent is not None
                else ""
            )
            lines.append(
                f"  - تعداد {point.quoted_quantity:,}: {normalized}{change} — "
                f"[{_text(point.source_name)}]({_link_target(point.source_url)})"
            )
    lines.append("- بازه سفارش اقتصادی: محاسبه نشده")
    lines.extend(f"- محدودیت: {_text(item)}" for item in quantity_analysis.limitations)

    lines.extend(["", "## فرض‌ها", ""])
    lines.extend(f"- {_text(item)}" for item in case.assumptions)
    if not case.assumptions:
        lines.append("- موردی ثبت نشده است.")

    lines.extend(["", "## مجهولات و نیاز به بررسی انسانی", ""])
    lines.extend(f"- {_text(item)}" for item in case.unknowns)
    if not case.unknowns:
        lines.append("- موردی ثبت نشده است.")

    lines.extend(
        [
            "",
            "> این گزارش تصمیم‌یار است. اعداد بر اساس شواهد و فرض‌های نمایش‌داده‌شده‌اند؛ ",
            "> قبل از خرید، قیمت، تعرفه، مجوز، حمل و امکان پرداخت باید دوباره تأیید شوند.",
            "",
        ]
    )
    return "\n".join(lines)
