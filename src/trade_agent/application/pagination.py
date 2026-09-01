from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from trade_agent.domain.errors import PublicInputError

MAX_CURSOR_LENGTH = 512


@dataclass(frozen=True, slots=True)
class PageCursor:
    created_at: datetime
    record_id: str


def encode_cursor(created_at: datetime, record_id: str) -> str:
    normalized = created_at
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    else:
        normalized = normalized.astimezone(UTC)
    payload = json.dumps(
        {"created_at": normalized.isoformat(), "id": record_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(value: str | None) -> PageCursor | None:
    if value is None:
        return None
    if not value or len(value) > MAX_CURSOR_LENGTH:
        raise PublicInputError("invalid pagination cursor")
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {"created_at", "id"}:
            raise ValueError
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        if created_at.tzinfo is None:
            raise ValueError
        record_id = str(UUID(str(payload["id"])))
    except (
        binascii.Error,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        raise PublicInputError("invalid pagination cursor") from None
    return PageCursor(created_at=created_at.astimezone(UTC), record_id=record_id)
