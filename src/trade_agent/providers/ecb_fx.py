from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx

from trade_agent.domain.models import Confidence, Evidence, EvidenceClass, FXRate
from trade_agent.providers.errors import ProviderUnavailableError
from trade_agent.providers.http import (
    ResponseTooLargeError,
    SafeHttpClient,
    UnsafeUrlError,
)

ECB_HOST = "data-api.ecb.europa.eu"
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class EcbFxProvider:
    def __init__(self, http_client: SafeHttpClient | None = None) -> None:
        self._http = http_client or SafeHttpClient(allowed_hosts={ECB_HOST})

    def latest_reference_rate(self, quote_currency: str) -> FXRate:
        currency = quote_currency.strip().upper()
        if currency == "EUR" or not _CURRENCY.fullmatch(currency):
            raise ValueError("quote currency must be a non-EUR three-letter code")
        url = (
            f"https://{ECB_HOST}/service/data/EXR/D.{currency}.EUR.SP00.A"
            "?format=csvdata&detail=dataonly&lastNObservations=1"
        )
        try:
            fetched = self._http.get(url)
            row = self._parse_latest(fetched.body)
            period = row["TIME_PERIOD"]
            value = Decimal(row["OBS_VALUE"])
            effective_at = datetime.fromisoformat(period).replace(tzinfo=UTC)
            retrieved_at = datetime.now(UTC)
            evidence = Evidence(
                classification=EvidenceClass.FACT,
                source_name="European Central Bank Data Portal",
                source_url=fetched.url,
                retrieved_at=retrieved_at,
                raw_value=json.dumps(row, ensure_ascii=False, sort_keys=True),
                confidence=Confidence.HIGH,
                transformation="ECB EXR daily reference observation parsed from SDMX CSV",
            )
            return FXRate(
                base_currency="EUR",
                quote_currency=currency,
                rate=value,
                evidence=evidence,
                rate_type="ECB_DAILY_REFERENCE_INFORMATIONAL",
                effective_at=effective_at,
            )
        except (
            csv.Error,
            httpx.HTTPError,
            InvalidOperation,
            KeyError,
            ResponseTooLargeError,
            UnicodeError,
            UnsafeUrlError,
            ValueError,
        ) as exc:
            raise ProviderUnavailableError(
                "ECB reference-rate service returned no usable observation"
            ) from exc

    @staticmethod
    def _parse_latest(body: bytes) -> dict[str, str]:
        text = body.decode("utf-8-sig")
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
        valid = [row for row in rows if row.get("TIME_PERIOD") and row.get("OBS_VALUE")]
        if not valid:
            raise ValueError("ECB response contained no observations")
        return dict(max(valid, key=lambda row: row["TIME_PERIOD"]))
