from __future__ import annotations

import re
from dataclasses import dataclass

from trade_agent.domain.models import Confidence

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_SPACE = re.compile(r"\s+")
_QUANTITY = re.compile(
    r"(?P<number>\d[\d,٬]*)\s*"
    r"(?P<unit>عدد|دستگاه|واحد|قطعه|کارتن|ست|pcs?|pieces?|units?|sets?)",
    re.IGNORECASE,
)
_ORIGIN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:از|مبدا|مبدأ)\s*(?:کشور\s*)?چین"), "چین"),
    (re.compile(r"(?:از|مبدا|مبدأ)\s*(?:کشور\s*)?(?:امارات|دبی)"), "امارات"),
    (re.compile(r"(?:از|مبدا|مبدأ)\s*(?:کشور\s*)?ترکیه"), "ترکیه"),
    (re.compile(r"\bfrom\s+china\b", re.IGNORECASE), "China"),
    (re.compile(r"\bfrom\s+(?:uae|dubai)\b", re.IGNORECASE), "UAE"),
    (re.compile(r"\bfrom\s+turkey\b", re.IGNORECASE), "Turkey"),
)
_DESTINATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:به\s+مقصد|مقصد|کف\s+انبار|تحویل\s+در|به)\s*"
        r"(?P<value>تهران|مشهد|اصفهان|شیراز|تبریز|کرج|بندرعباس|ایران)"
    ),
    re.compile(
        r"\b(?:to|delivered\s+to)\s+"
        r"(?P<value>tehran|mashhad|isfahan|shiraz|tabriz|iran)\b",
        re.IGNORECASE,
    ),
)
_PRODUCT_STOP = re.compile(
    r"(?:^|\s+)(?:از|مبدا|مبدأ|به|برای|جهت|با|تحویل|تهیه|خرید|سفارش|و\s+می|و\s+بهای|"
    r"from|to|for|with|delivered|and)\b",
    re.IGNORECASE,
)
_LEADING_INTENT = re.compile(
    r"^(?:می\s*خواهم|میخوام|قصد\s+دارم|لطفا|لطفاً|please|i\s+want|i\s+need|"
    r"source|buy|purchase|قیمت|خرید|تهیه)\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedTradeRequest:
    original_text: str
    normalized_text: str
    product_name: str | None
    quantity: int | None
    quantity_unit: str | None
    origin_market: str | None
    destination: str | None
    field_confidence: dict[str, Confidence]
    assumptions: tuple[str, ...]
    critical_questions: tuple[str, ...]

    @property
    def can_start_research(self) -> bool:
        return not self.critical_questions


def _normalize(text: str) -> str:
    normalized = text.translate(_DIGITS).replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")
    return _SPACE.sub(" ", normalized).strip()


def _extract_product(text: str, quantity_match: re.Match[str] | None) -> str | None:
    candidate = ""
    if quantity_match is not None:
        tail = text[quantity_match.end() :].strip(" ،,:؛-")
        candidate = _PRODUCT_STOP.split(tail, maxsplit=1)[0].strip(" ،,:؛-.")
        if not candidate:
            prefix = text[: quantity_match.start()].strip(" ،,:؛-.")
            prefix = re.sub(r"(?:تعداد|quantity)\s*$", "", prefix, flags=re.IGNORECASE).strip()
            while True:
                reduced = _LEADING_INTENT.sub("", prefix).strip(" ،,:؛-.")
                if reduced == prefix:
                    break
                prefix = reduced
            candidate = prefix
    else:
        candidate = text.strip(" ،,:؛-.")
        while True:
            reduced = _LEADING_INTENT.sub("", candidate).strip(" ،,:؛-.")
            if reduced == candidate:
                break
            candidate = reduced
        candidate = _PRODUCT_STOP.split(candidate, maxsplit=1)[0].strip(" ،,:؛-.")
    if not candidate:
        return None
    if candidate.casefold() in {"واردات", "برای واردات", "قیمت", "import", "sourcing"}:
        return None
    if len(candidate) > 300:
        raise ValueError("extracted product name is too long")
    return candidate


def parse_trade_request(text: str) -> ParsedTradeRequest:
    if not text or not text.strip():
        raise ValueError("request text is required")
    if len(text) > 5000:
        raise ValueError("request text exceeds 5000 characters")
    normalized = _normalize(text)
    quantity_match = _QUANTITY.search(normalized)
    quantity: int | None = None
    quantity_unit: str | None = None
    if quantity_match is not None:
        quantity = int(quantity_match.group("number").replace(",", "").replace("٬", ""))
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        quantity_unit = quantity_match.group("unit")

    origin = next(
        (value for pattern, value in _ORIGIN_PATTERNS if pattern.search(normalized)), None
    )
    destination = next(
        (
            match.group("value")
            for pattern in _DESTINATION_PATTERNS
            if (match := pattern.search(normalized)) is not None
        ),
        None,
    )
    product = _extract_product(normalized, quantity_match)

    confidence = {
        "product_name": Confidence.HIGH if product else Confidence.UNKNOWN,
        "quantity": Confidence.HIGH if quantity is not None else Confidence.UNKNOWN,
        "origin_market": Confidence.HIGH if origin else Confidence.UNKNOWN,
        "destination": Confidence.HIGH if destination else Confidence.UNKNOWN,
    }
    assumptions = () if origin else ("بازار مبدأ هنوز مشخص نشده است.",)
    questions: list[str] = []
    if product is None:
        questions.append("نام و مشخصات اصلی کالای موردنظر چیست؟")
    if quantity is None:
        questions.append("چه تعداد از کالا را می‌خواهید بررسی کنید؟")
    if destination is None:
        questions.append("مقصد نهایی محاسبه بهای تمام‌شده کجاست؟")
    return ParsedTradeRequest(
        original_text=text,
        normalized_text=normalized,
        product_name=product,
        quantity=quantity,
        quantity_unit=quantity_unit,
        origin_market=origin,
        destination=destination,
        field_confidence=confidence,
        assumptions=assumptions,
        critical_questions=tuple(questions),
    )
