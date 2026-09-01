from __future__ import annotations

import re
from dataclasses import dataclass

from trade_agent.application.incoterms import INCOTERMS_2020_CODES
from trade_agent.domain.errors import PublicInputError
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
_EXPLICIT_ORIGIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:از\s+کشور|مبدا|مبدأ)\s*[:：]?\s*"
        r"(?P<value>.+?)(?=\s*(?:،|,|؛|;|\.|\b(?:به|برای|جهت|تحویل|تهیه|خرید|و)\b|$))"
    ),
    re.compile(
        r"\b(?:from|origin(?:\s+market)?)\s*[:：]?\s*"
        r"(?P<value>.+?)(?=\s*(?:,|;|\.|\b(?:to|delivered|for|with|and)\b|$))",
        re.IGNORECASE,
    ),
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
_EXPLICIT_DESTINATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:به\s+مقصد|مقصد|کف\s+انبار|تحویل\s+در)\s*[:：]?\s*"
        r"(?P<value>.+?)(?=\s*(?:،|,|؛|;|\.|\b(?:را|برای|جهت|با|و)\b|$))"
    ),
    re.compile(
        r"\b(?:delivered\s+to|destination)\s*[:：]?\s*"
        r"(?P<value>.+?)(?=\s*(?:,|;|\.|\b(?:for|with|and)\b|$))",
        re.IGNORECASE,
    ),
)
_ORIGIN_ALIASES = {
    "china": "China",
    "uae": "UAE",
    "dubai": "UAE",
    "turkey": "Turkey",
    "چین": "چین",
    "امارات": "امارات",
    "دبی": "امارات",
    "ترکیه": "ترکیه",
}
_DESTINATION_ALIASES = {
    "tehran": "Tehran",
    "mashhad": "Mashhad",
    "isfahan": "Isfahan",
    "shiraz": "Shiraz",
    "tabriz": "Tabriz",
    "iran": "Iran",
}
_INCOTERM_MARKER = re.compile(
    r"(?:اینکوترمز|شرط\s+تحویل|incoterms?|delivery\s+term)",
    re.IGNORECASE,
)
_INCOTERM_CLAUSE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:اینکوترمز|شرط\s+تحویل)\s*[:：]?\s*"
        r"(?P<value>.+?)(?=\s*(?:،|,|؛|;|\.|\b(?:به|مقصد|کف|تحویل|از|مبدا|مبدأ)\b|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:incoterms?|delivery\s+term)\s*[:：]?\s*"
        r"(?P<value>.+?)(?=\s*(?:,|;|\.|\b(?:to|destination|delivered|from|origin)\b|$))",
        re.IGNORECASE,
    ),
)
_INCOTERM_CODE = re.compile(
    rf"\b(?:{'|'.join(INCOTERMS_2020_CODES)})\b",
    re.IGNORECASE,
)
_PRODUCT_STOP = re.compile(
    r"(?:^|\s+)(?:از|مبدا|مبدأ|به|برای|جهت|با|تحویل|تهیه|خرید|سفارش|و\s+می|و\s+بهای|"
    r"اینکوترمز|شرط\s+تحویل|from|to|for|with|delivered|and|incoterms?|"
    r"delivery\s+term)\b",
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
    requested_incoterm_code: str | None
    field_confidence: dict[str, Confidence]
    field_conflicts: dict[str, tuple[str, ...]]
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
        raise PublicInputError("extracted product name is too long")
    return candidate


def _normalize_location(value: str, aliases: dict[str, str]) -> str:
    normalized = _SPACE.sub(" ", value).strip(" \t\r\n،,:؛;.-")
    if not normalized:
        raise PublicInputError("explicit location cannot be empty")
    if len(normalized) > 100:
        raise PublicInputError("explicit location exceeds 100 characters")
    return aliases.get(normalized.casefold(), normalized)


def _ordered_unique_values(values: list[tuple[int, str]]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for _, value in sorted(values, key=lambda item: item[0]):
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return tuple(unique)


def _extract_origin_candidates(text: str) -> tuple[str, ...]:
    matches: list[tuple[int, str]] = []
    for pattern, canonical in _ORIGIN_PATTERNS:
        matches.extend((match.start(), canonical) for match in pattern.finditer(text))
    for pattern in _EXPLICIT_ORIGIN_PATTERNS:
        matches.extend(
            (
                match.start(),
                _normalize_location(match.group("value"), _ORIGIN_ALIASES),
            )
            for match in pattern.finditer(text)
        )
    return _ordered_unique_values(matches)


def _extract_destination_candidates(text: str) -> tuple[str, ...]:
    matches: list[tuple[int, str]] = []
    for pattern in _DESTINATION_PATTERNS:
        matches.extend(
            (
                match.start(),
                _normalize_location(match.group("value"), _DESTINATION_ALIASES),
            )
            for match in pattern.finditer(text)
        )
    for pattern in _EXPLICIT_DESTINATION_PATTERNS:
        matches.extend(
            (
                match.start(),
                _normalize_location(match.group("value"), _DESTINATION_ALIASES),
            )
            for match in pattern.finditer(text)
        )
    return _ordered_unique_values(matches)


def _extract_incoterm_candidates(text: str) -> tuple[tuple[str, ...], bool]:
    marker_present = _INCOTERM_MARKER.search(text) is not None
    matches: list[tuple[int, str]] = []
    for pattern in _INCOTERM_CLAUSE_PATTERNS:
        for clause in pattern.finditer(text):
            matches.extend(
                (clause.start("value") + match.start(), match.group().upper())
                for match in _INCOTERM_CODE.finditer(clause.group("value"))
            )
    return _ordered_unique_values(matches), marker_present


def parse_trade_request(text: str) -> ParsedTradeRequest:
    if not text or not text.strip():
        raise PublicInputError("request text is required")
    if len(text) > 5000:
        raise PublicInputError("request text exceeds 5000 characters")
    normalized = _normalize(text)
    quantity_match = _QUANTITY.search(normalized)
    quantity: int | None = None
    quantity_unit: str | None = None
    if quantity_match is not None:
        quantity = int(quantity_match.group("number").replace(",", "").replace("٬", ""))
        if quantity <= 0:
            raise PublicInputError("quantity must be positive")
        quantity_unit = quantity_match.group("unit")

    origin_candidates = _extract_origin_candidates(normalized)
    destination_candidates = _extract_destination_candidates(normalized)
    incoterm_candidates, incoterm_marker_present = _extract_incoterm_candidates(normalized)
    origin = origin_candidates[0] if len(origin_candidates) == 1 else None
    destination = destination_candidates[0] if len(destination_candidates) == 1 else None
    requested_incoterm = (
        incoterm_candidates[0] if len(incoterm_candidates) == 1 else None
    )
    product = _extract_product(normalized, quantity_match)

    field_conflicts: dict[str, tuple[str, ...]] = {}
    if len(origin_candidates) > 1:
        field_conflicts["origin_market"] = origin_candidates
    if len(destination_candidates) > 1:
        field_conflicts["destination"] = destination_candidates
    if len(incoterm_candidates) > 1:
        field_conflicts["requested_incoterm_code"] = incoterm_candidates

    confidence = {
        "product_name": Confidence.HIGH if product else Confidence.UNKNOWN,
        "quantity": Confidence.HIGH if quantity is not None else Confidence.UNKNOWN,
        "origin_market": Confidence.HIGH if origin else Confidence.UNKNOWN,
        "destination": Confidence.HIGH if destination else Confidence.UNKNOWN,
        "requested_incoterm_code": (
            Confidence.HIGH if requested_incoterm else Confidence.UNKNOWN
        ),
    }
    assumptions = ("بازار مبدأ هنوز مشخص نشده است.",) if not origin_candidates else ()
    questions: list[str] = []
    if product is None:
        questions.append("نام و مشخصات اصلی کالای موردنظر چیست؟")
    if quantity is None:
        questions.append("چه تعداد از کالا را می‌خواهید بررسی کنید؟")
    if "origin_market" in field_conflicts:
        questions.append("چند مبدأ متفاوت تشخیص داده شد؛ مبدأ نهایی کدام است؟")
    if "destination" in field_conflicts:
        questions.append("چند مقصد متفاوت تشخیص داده شد؛ مقصد نهایی کدام است؟")
    elif destination is None:
        questions.append("مقصد نهایی محاسبه بهای تمام‌شده کجاست؟")
    if "requested_incoterm_code" in field_conflicts:
        questions.append("چند کد Incoterm متفاوت اعلام شده است؛ کد نهایی کدام است؟")
    elif incoterm_marker_present and not incoterm_candidates:
        questions.append("کد معتبر Incoterm موردنظر چیست؟")
    return ParsedTradeRequest(
        original_text=text,
        normalized_text=normalized,
        product_name=product,
        quantity=quantity,
        quantity_unit=quantity_unit,
        origin_market=origin,
        destination=destination,
        requested_incoterm_code=requested_incoterm,
        field_confidence=confidence,
        field_conflicts=field_conflicts,
        assumptions=assumptions,
        critical_questions=tuple(questions),
    )
