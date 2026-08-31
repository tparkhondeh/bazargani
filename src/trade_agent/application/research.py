from __future__ import annotations

from dataclasses import dataclass

from trade_agent.calculation.landed_cost import calculate_landed_cost
from trade_agent.domain.models import LandedCostResult, ResearchCase, ScenarioName


@dataclass(frozen=True, slots=True)
class ResearchResult:
    case: ResearchCase
    scenarios: tuple[LandedCostResult, ...]


def execute_research_case(case: ResearchCase) -> ResearchResult:
    names = {scenario.name for scenario in case.scenarios}
    required = {ScenarioName.OPTIMISTIC, ScenarioName.BASE, ScenarioName.CONSERVATIVE}
    missing = required - names
    if missing:
        raise ValueError(f"missing required scenarios: {', '.join(sorted(missing))}")

    eligible = [
        observation
        for observation in case.observations
        if observation.minimum_order_quantity is None
        or case.quantity >= observation.minimum_order_quantity
    ]
    if not eligible:
        raise ValueError("no price observation is eligible for the requested quantity")

    calculated = tuple(calculate_landed_cost(scenario) for scenario in case.scenarios)
    return ResearchResult(case=case, scenarios=calculated)
