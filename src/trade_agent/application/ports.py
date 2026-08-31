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
    fx_rate_count: int
    scenario_count: int
    report_sha256: str


class ResearchResultWriter(Protocol):
    def persist_research_result(
        self,
        *,
        run_id: str,
        result: ResearchResult,
        report_markdown: str,
        expected_version: int,
        correlation_id: str,
    ) -> ResearchCompletion: ...
