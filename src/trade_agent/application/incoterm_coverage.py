from __future__ import annotations

from dataclasses import dataclass

from trade_agent.application.incoterms import (
    INCOTERMS_2020_CODES,
    INCOTERMS_REFERENCE_VERSION,
)
from trade_agent.domain.errors import PublicInputError


@dataclass(frozen=True, slots=True)
class IncotermEvidencePoint:
    observation_id: str
    incoterm: str | None
    incoterm_named_place: str | None
    incoterm_version: str | None
    supplier_name: str | None
    source_url: str


@dataclass(frozen=True, slots=True)
class IncotermEvidenceGroup:
    code: str
    recognized: bool
    observation_ids: tuple[str, ...]
    supplier_names: tuple[str, ...]
    source_urls: tuple[str, ...]
    named_places: tuple[str, ...]
    declared_versions: tuple[str, ...]
    offer_count: int
    named_supplier_count: int
    distinct_source_count: int
    named_place_observation_count: int
    version_observation_count: int
    complete_terms_observation_count: int


@dataclass(frozen=True, slots=True)
class IncotermCoverageSummary:
    status: str
    reference_version: str
    reference_codes: tuple[str, ...]
    observed_recognized_codes: tuple[str, ...]
    unrecognized_declared_codes: tuple[str, ...]
    groups: tuple[IncotermEvidenceGroup, ...]
    missing_incoterm_observation_ids: tuple[str, ...]
    missing_named_place_observation_ids: tuple[str, ...]
    missing_version_observation_ids: tuple[str, ...]
    comparison_status: str
    limitations: tuple[str, ...]


def summarize_incoterm_coverage(
    points: tuple[IncotermEvidencePoint, ...],
) -> IncotermCoverageSummary:
    observation_ids = [point.observation_id for point in points]
    if len(observation_ids) != len(set(observation_ids)):
        raise PublicInputError("incoterm-coverage observation IDs must be unique")

    reference_set = set(INCOTERMS_2020_CODES)
    grouped: dict[str, list[IncotermEvidencePoint]] = {}
    missing: list[str] = []
    missing_named_place: list[str] = []
    missing_version: list[str] = []
    for point in points:
        code = (point.incoterm or "").strip().upper()
        if not code:
            missing.append(point.observation_id)
            continue
        grouped.setdefault(code, []).append(point)
        if not point.incoterm_named_place or not point.incoterm_named_place.strip():
            missing_named_place.append(point.observation_id)
        if not point.incoterm_version or not point.incoterm_version.strip():
            missing_version.append(point.observation_id)

    code_order = {code: index for index, code in enumerate(INCOTERMS_2020_CODES)}
    groups: list[IncotermEvidenceGroup] = []
    for code, group in sorted(
        grouped.items(),
        key=lambda item: (code_order.get(item[0], len(code_order)), item[0]),
    ):
        ordered = sorted(group, key=lambda point: point.observation_id)
        supplier_names = tuple(
            sorted(
                {
                    point.supplier_name.strip()
                    for point in ordered
                    if point.supplier_name and point.supplier_name.strip()
                }
            )
        )
        source_urls = tuple(sorted({point.source_url for point in ordered}))
        named_places = tuple(
            sorted(
                {
                    point.incoterm_named_place.strip()
                    for point in ordered
                    if point.incoterm_named_place
                    and point.incoterm_named_place.strip()
                }
            )
        )
        declared_versions = tuple(
            sorted(
                {
                    point.incoterm_version.strip()
                    for point in ordered
                    if point.incoterm_version and point.incoterm_version.strip()
                }
            )
        )
        groups.append(
            IncotermEvidenceGroup(
                code=code,
                recognized=code in reference_set,
                observation_ids=tuple(point.observation_id for point in ordered),
                supplier_names=supplier_names,
                source_urls=source_urls,
                named_places=named_places,
                declared_versions=declared_versions,
                offer_count=len(ordered),
                named_supplier_count=len(supplier_names),
                distinct_source_count=len(source_urls),
                named_place_observation_count=sum(
                    bool(
                        point.incoterm_named_place
                        and point.incoterm_named_place.strip()
                    )
                    for point in ordered
                ),
                version_observation_count=sum(
                    bool(point.incoterm_version and point.incoterm_version.strip())
                    for point in ordered
                ),
                complete_terms_observation_count=sum(
                    bool(
                        point.incoterm_named_place
                        and point.incoterm_named_place.strip()
                        and point.incoterm_version
                        and point.incoterm_version.strip()
                    )
                    for point in ordered
                ),
            )
        )

    if not points:
        status = "NO_PRICE_OBSERVATIONS"
    elif not groups:
        status = "NO_DECLARED_INCOTERMS"
    else:
        status = "OBSERVED_INCOTERM_COVERAGE"
    return IncotermCoverageSummary(
        status=status,
        reference_version=INCOTERMS_REFERENCE_VERSION,
        reference_codes=INCOTERMS_2020_CODES,
        observed_recognized_codes=tuple(code for code in INCOTERMS_2020_CODES if code in grouped),
        unrecognized_declared_codes=tuple(
            sorted(code for code in grouped if code not in reference_set)
        ),
        groups=tuple(groups),
        missing_incoterm_observation_ids=tuple(sorted(missing)),
        missing_named_place_observation_ids=tuple(sorted(missing_named_place)),
        missing_version_observation_ids=tuple(sorted(missing_version)),
        comparison_status="WITHHELD_NO_INCOTERM_SCENARIOS",
        limitations=(
            "coverage summarizes submitted declarations and does not verify contract "
            "wording or execution",
            "declared code, named place, and version do not prove agreed contract terms",
            "distinct source URLs do not prove source independence",
            "no best Incoterm is selected without comparable route-specific cost, "
            "control, and risk scenarios",
        ),
    )
