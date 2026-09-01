from __future__ import annotations

import re

from fastapi.exceptions import RequestValidationError

from trade_agent.api.schemas import ValidationErrorDetail

MAX_VALIDATION_DETAILS = 50
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_SAFE_LOCATION_NAMES = frozenset(
    {
        "after",
        "body",
        "bundle",
        "cookie",
        "decision",
        "expected_version",
        "header",
        "idempotency-key",
        "limit",
        "opportunity_id",
        "path",
        "product_name",
        "quantity",
        "query",
        "quote_currency",
        "rationale",
        "run_id",
        "target_market",
        "target_status",
        "text",
    }
)
_SAFE_MESSAGES = {
    "missing": "field is required",
    "extra_forbidden": "unexpected field",
    "json_invalid": "request body is not valid JSON",
}


def safe_validation_details(exc: RequestValidationError) -> list[ValidationErrorDetail]:
    raw_errors = exc.errors()
    details: list[ValidationErrorDetail] = []
    for raw in raw_errors[:MAX_VALIDATION_DETAILS]:
        raw_type = str(raw.get("type", "validation_error"))
        code = raw_type if _SAFE_TOKEN.fullmatch(raw_type) else "validation_error"
        location = [_safe_location_part(part) for part in raw.get("loc", ())]
        details.append(
            ValidationErrorDetail(
                location=location,
                code=code,
                message=_SAFE_MESSAGES.get(code, "invalid value"),
            )
        )
    if len(raw_errors) > MAX_VALIDATION_DETAILS:
        details.append(
            ValidationErrorDetail(
                location=[],
                code="additional_errors_omitted",
                message="additional validation errors were omitted",
            )
        )
    return details


def _safe_location_part(part: object) -> str:
    if isinstance(part, int):
        return str(part)
    value = str(part)
    return value if value.casefold() in _SAFE_LOCATION_NAMES else "field"
