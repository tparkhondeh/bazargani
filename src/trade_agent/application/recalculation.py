from __future__ import annotations

import hashlib
import json

from trade_agent.application.ports import (
    SuccessorResearchRun,
    SuccessorResearchRunWriter,
)
from trade_agent.domain.errors import PublicInputError


def create_successor_research_run(
    writer: SuccessorResearchRunWriter,
    *,
    source_run_id: str,
    reason: str,
    expected_version: int,
    correlation_id: str,
    idempotency_key: str,
    tenant_id: str,
    actor_id: str,
) -> SuccessorResearchRun:
    normalized_reason = reason.strip()
    if not 3 <= len(normalized_reason) <= 2_000:
        raise PublicInputError("recalculation reason must contain 3 to 2000 characters")
    canonical_request = json.dumps(
        {
            "expected_version": expected_version,
            "reason": normalized_reason,
            "source_run_id": source_run_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    replay = writer.replay_successor_research_run(
        source_run_id=source_run_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        tenant_id=tenant_id,
    )
    if replay is not None:
        return replay
    return writer.persist_successor_research_run(
        source_run_id=source_run_id,
        reason=normalized_reason,
        expected_version=expected_version,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        tenant_id=tenant_id,
        actor_id=actor_id,
    )
