from __future__ import annotations

import html
import re
from urllib.parse import quote

from trade_agent.application.research import ResearchResult

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
