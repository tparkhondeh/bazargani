from __future__ import annotations

from dataclasses import dataclass

from trade_agent.domain.errors import PublicInputError

REFERENCE_COMPONENT_CODES = (
    "product_cost",
    "origin_charges",
    "packaging",
    "inspection",
    "documentation",
    "inland_origin_transport",
    "export_charges",
    "freight",
    "insurance",
    "tariff_duty",
    "taxes",
    "import_fees",
    "port_terminal_charges",
    "broker_clearance",
    "storage",
    "payment_costs",
    "fx_costs",
    "sanctions_costs",
    "domestic_transport",
    "unexpected_cost",
    "other_explicit_cost",
)
_EVIDENCE_CLASSES = (
    "FACT",
    "ESTIMATE",
    "ASSUMPTION",
    "DERIVED_CALCULATION",
    "AI_INFERENCE",
)
_SCENARIO_ORDER = {"OPTIMISTIC": 0, "BASE": 1, "CONSERVATIVE": 2}


@dataclass(frozen=True, slots=True)
class CostCoveragePoint:
    code: str
    evidence_class: str
    is_zero: bool


@dataclass(frozen=True, slots=True)
class ScenarioCostCoverageInput:
    name: str
    components: tuple[CostCoveragePoint, ...]


@dataclass(frozen=True, slots=True)
class ScenarioCostCoverage:
    name: str
    recorded_component_codes: tuple[str, ...]
    recognized_reference_codes: tuple[str, ...]
    unrecorded_reference_codes: tuple[str, ...]
    unclassified_component_codes: tuple[str, ...]
    zero_amount_codes: tuple[str, ...]
    recorded_component_count: int
    fact_count: int
    estimate_count: int
    assumption_count: int
    derived_calculation_count: int
    ai_inference_count: int


@dataclass(frozen=True, slots=True)
class TradeCostCoverage:
    status: str
    reference_component_codes: tuple[str, ...]
    scenarios: tuple[ScenarioCostCoverage, ...]
    limitations: tuple[str, ...]


def analyze_trade_cost_coverage(
    scenarios: tuple[ScenarioCostCoverageInput, ...],
) -> TradeCostCoverage:
    names = [scenario.name for scenario in scenarios]
    if len(names) != len(set(names)):
        raise PublicInputError("cost-coverage scenario names must be unique")

    reference_set = set(REFERENCE_COMPONENT_CODES)
    results: list[ScenarioCostCoverage] = []
    for scenario in sorted(
        scenarios,
        key=lambda item: (_SCENARIO_ORDER.get(item.name, 99), item.name),
    ):
        invalid_classes = sorted(
            {
                component.evidence_class
                for component in scenario.components
                if component.evidence_class not in _EVIDENCE_CLASSES
            }
        )
        if invalid_classes:
            raise PublicInputError("unsupported cost-component evidence class")
        codes = tuple(sorted({component.code for component in scenario.components}))
        recognized = tuple(code for code in REFERENCE_COMPONENT_CODES if code in codes)
        results.append(
            ScenarioCostCoverage(
                name=scenario.name,
                recorded_component_codes=codes,
                recognized_reference_codes=recognized,
                unrecorded_reference_codes=tuple(
                    code for code in REFERENCE_COMPONENT_CODES if code not in codes
                ),
                unclassified_component_codes=tuple(
                    code for code in codes if code not in reference_set
                ),
                zero_amount_codes=tuple(
                    sorted(
                        {
                            component.code
                            for component in scenario.components
                            if component.is_zero
                        }
                    )
                ),
                recorded_component_count=len(scenario.components),
                fact_count=sum(
                    component.evidence_class == "FACT"
                    for component in scenario.components
                ),
                estimate_count=sum(
                    component.evidence_class == "ESTIMATE"
                    for component in scenario.components
                ),
                assumption_count=sum(
                    component.evidence_class == "ASSUMPTION"
                    for component in scenario.components
                ),
                derived_calculation_count=sum(
                    component.evidence_class == "DERIVED_CALCULATION"
                    for component in scenario.components
                ),
                ai_inference_count=sum(
                    component.evidence_class == "AI_INFERENCE"
                    for component in scenario.components
                ),
            )
        )

    return TradeCostCoverage(
        status="RECORDED_COST_COMPONENT_COVERAGE" if results else "NO_COST_SCENARIOS",
        reference_component_codes=REFERENCE_COMPONENT_CODES,
        scenarios=tuple(results),
        limitations=(
            "unrecorded reference codes are not automatically required or applicable",
            "no missing amount is inferred and custom component codes remain visible",
            "component presence does not prove tariff, tax, customs, or compliance correctness",
        ),
    )
