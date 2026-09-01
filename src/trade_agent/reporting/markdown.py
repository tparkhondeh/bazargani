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
