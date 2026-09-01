from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trade_agent.application.research import ResearchResult


@dataclass(frozen=True, slots=True)
class ResearchCompletion:
    research_run_id: str
    status: str
    version: int
    evidence_count: int
    price_observation_count: int
    product_match_count: int
    supplier_ranking_count: int
    fx_rate_count: int
    scenario_count: int
    validation_disposition: str
    validation_issue_count: int
    confidence_score: int
    confidence_label: str
    report_sha256: str
    idempotency_replayed: bool


class ResearchResultWriter(Protocol):
    def replay_research_result(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        request_hash: str,
        tenant_id: str,
    ) -> ResearchCompletion | None: ...

    def persist_research_result(
        self,
        *,
        run_id: str,
        result: ResearchResult,
        report_markdown: str,
        expected_version: int,
        correlation_id: str,
        idempotency_key: str,
        request_hash: str,
        tenant_id: str,
        actor_id: str,
    ) -> ResearchCompletion: ...
