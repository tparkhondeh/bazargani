from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trade_agent.application.validation import ValidationResult, validate_research_case
from trade_agent.calculation.landed_cost import calculate_landed_cost
from trade_agent.domain.models import LandedCostResult, ResearchCase, ScenarioName


@dataclass(frozen=True, slots=True)
class ResearchResult:
    case: ResearchCase
    scenarios: tuple[LandedCostResult, ...]
    validation: ValidationResult


def execute_research_case(
    case: ResearchCase, *, evaluated_at: datetime | None = None
) -> ResearchResult:
    names = {scenario.name for scenario in case.scenarios}
    required = {ScenarioName.OPTIMISTIC, ScenarioName.BASE, ScenarioName.CONSERVATIVE}
    missing = required - names
    if missing:
        raise ValueError(f"missing required scenarios: {', '.join(sorted(missing))}")

    clean_case, validation = validate_research_case(case, evaluated_at=evaluated_at)
    calculated = tuple(calculate_landed_cost(scenario) for scenario in clean_case.scenarios)
    return ResearchResult(case=clean_case, scenarios=calculated, validation=validation)
