from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trade_agent.application.matching import match_research_case
from trade_agent.application.ranking import rank_supplier_offers
from trade_agent.application.validation import (
    ValidationResult,
    validate_product_matches,
    validate_research_case,
    validate_supplier_rankings,
)
from trade_agent.calculation.landed_cost import calculate_landed_cost
from trade_agent.domain.errors import PublicInputError
from trade_agent.domain.models import (
    LandedCostResult,
    ProductMatch,
    ResearchCase,
    ScenarioName,
    SupplierOfferRanking,
)


@dataclass(frozen=True, slots=True)
class ResearchResult:
    case: ResearchCase
    scenarios: tuple[LandedCostResult, ...]
    product_matches: tuple[ProductMatch, ...]
    supplier_rankings: tuple[SupplierOfferRanking, ...]
    validation: ValidationResult


def execute_research_case(
    case: ResearchCase, *, evaluated_at: datetime | None = None
) -> ResearchResult:
    names = {scenario.name for scenario in case.scenarios}
    required = {ScenarioName.OPTIMISTIC, ScenarioName.BASE, ScenarioName.CONSERVATIVE}
    missing = required - names
    if missing:
        raise PublicInputError(f"missing required scenarios: {', '.join(sorted(missing))}")
    if len(names) != len(case.scenarios):
        raise PublicInputError("scenario names must be unique within a research case")

    clean_case, validation = validate_research_case(case, evaluated_at=evaluated_at)
    matches = match_research_case(clean_case)
    validation = validate_product_matches(validation, matches)
    rankings = rank_supplier_offers(clean_case, matches)
    validation = validate_supplier_rankings(validation, rankings)
    calculated = tuple(calculate_landed_cost(scenario) for scenario in clean_case.scenarios)
    return ResearchResult(
        case=clean_case,
        scenarios=calculated,
        product_matches=matches,
        supplier_rankings=rankings,
        validation=validation,
    )
