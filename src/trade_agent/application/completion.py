from __future__ import annotations

import hashlib
import json
from typing import Any

from trade_agent.application.ports import ResearchCompletion, ResearchResultWriter
from trade_agent.application.research import execute_research_case
from trade_agent.providers.evidence_bundle import parse_evidence_bundle
from trade_agent.reporting.markdown import render_markdown


def complete_research_run_from_bundle(
    writer: ResearchResultWriter,
    *,
    run_id: str,
    bundle: dict[str, Any],
    expected_version: int,
    correlation_id: str,
    idempotency_key: str,
) -> ResearchCompletion:
    canonical_request = json.dumps(
        {"bundle": bundle, "expected_version": expected_version, "run_id": run_id},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    replay = writer.replay_research_result(
        run_id=run_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay
    case = parse_evidence_bundle(bundle)
    result = execute_research_case(case)
    report = render_markdown(result)
    return writer.persist_research_result(
        run_id=run_id,
        result=result,
        report_markdown=report,
        expected_version=expected_version,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
