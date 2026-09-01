from __future__ import annotations

from trade_agent.application.research import ResearchResult


def render_markdown(result: ResearchResult) -> str:
    case = result.case
    validation = result.validation
    lines = [
        f"# گزارش تصمیم بازرگانی — {case.product_name}",
        "",
        f"- شناسه پرونده: `{case.case_id}`",
        f"- تعداد: {case.quantity:,}",
        f"- مقصد: {case.destination}",
        f"- تعداد مشاهدات قیمت: {len(case.observations)}",
        f"- وضعیت اعتبارسنجی: `{validation.disposition.value}`",
        f"- امتیاز اعتماد توضیح‌پذیر: {validation.confidence_score}/100 "
        f"(`{validation.confidence_label.value}`)",
        "",
        "## کیفیت داده و نیاز به بازبینی",
        "",
        f"- نسخه سیاست اعتبارسنجی: `{validation.policy_version}`",
        f"- زمان ارزیابی: {validation.evaluated_at.isoformat()}",
        "- روش امتیازدهی: شروع از ۱۰۰؛ هر هشدار ۱۰- و هر خطا ۳۰- (حداقل صفر).",
    ]
    if validation.issues:
        lines.extend(
            f"- **{issue.severity.value} / {issue.code}** "
            f"(`{issue.subject_type}:{issue.subject_id or '-'}`) — {issue.message_fa}"
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
        lines.extend([f"### {scenario.name.value}", ""])
        for component in scenario.components:
            lines.append(
                f"- {component.label_fa}: {component.amount.amount:,.2f} "
                f"{component.amount.currency} — `{component.evidence_class.value}`"
            )
        lines.append("")

    lines.extend(["## شواهد قیمت", ""])
    for observation in case.observations:
        lines.append(
            f"- [{observation.evidence.source_name}]({observation.evidence.source_url}): "
            f"{observation.unit_price.amount} {observation.unit_price.currency}، "
            f"واحد `{observation.unit}`، "
            f"کلاس `{observation.evidence.classification.value}`، "
            f"اعتماد `{observation.evidence.confidence.value}`"
        )

    lines.extend(["", "## تطبیق محصول", ""])
    if case.product_attributes:
        requested_attributes = "، ".join(
            f"`{key}={value}`" for key, value in sorted(case.product_attributes.items())
        )
        lines.append(f"- ویژگی‌های مرجع پرونده: {requested_attributes}")
    for match in result.product_matches:
        lines.append(
            f"- مشاهده `{match.observation_id}`: `{match.classification.value}`، "
            f"امتیاز {match.score}/100، شباهت نام {match.name_similarity:.2f}"
        )
        lines.extend(f"  - {reason}" for reason in match.explanation_fa)
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
            f"- {ranking.supplier_name or 'تأمین‌کننده نامشخص'} — رتبه {rank_label} در "
            f"`{ranking.comparison_group}`، امتیاز {ranking.total_score}/100، "
            f"قیمت واحد نرمال‌شده {normalized}"
        )
        component_text = "، ".join(
            f"{key}={value}" for key, value in sorted(ranking.component_scores.items())
        )
        lines.append(f"  - اجزای امتیاز: {component_text}")
        if ranking.unknown_factors:
            lines.append(f"  - عوامل نامشخص: {', '.join(ranking.unknown_factors)}")
        lines.extend(f"  - {reason}" for reason in ranking.explanation_fa)
    if not result.supplier_rankings:
        lines.append("- پیشنهادی برای رتبه‌بندی وجود ندارد.")

    lines.extend(["", "## فرض‌ها", ""])
    lines.extend(f"- {item}" for item in case.assumptions)
    if not case.assumptions:
        lines.append("- موردی ثبت نشده است.")

    lines.extend(["", "## مجهولات و نیاز به بررسی انسانی", ""])
    lines.extend(f"- {item}" for item in case.unknowns)
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
