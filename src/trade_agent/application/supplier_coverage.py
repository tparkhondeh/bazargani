from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupplierEvidencePoint:
    observation_id: str
    supplier_name: str | None
    source_url: str
    minimum_order_quantity: int | None
    incoterm: str | None
    rankable: bool
    unknown_factors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierEvidenceCoverage:
    supplier_name: str
    observation_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    offer_count: int
    distinct_source_count: int
    moq_observation_count: int
    incoterm_observation_count: int
    rankable_offer_count: int
    unknown_factors: tuple[str, ...]
    due_diligence_status: str


@dataclass(frozen=True, slots=True)
class SupplierCoverageSummary:
    status: str
    suppliers: tuple[SupplierEvidenceCoverage, ...]
    unidentified_observation_ids: tuple[str, ...]
    limitations: tuple[str, ...]


def summarize_supplier_coverage(
    points: tuple[SupplierEvidencePoint, ...],
) -> SupplierCoverageSummary:
    identified: dict[str, list[SupplierEvidencePoint]] = {}
    unidentified: list[str] = []
    for point in points:
        if point.supplier_name is None:
            unidentified.append(point.observation_id)
            continue
        identified.setdefault(point.supplier_name, []).append(point)

    suppliers: list[SupplierEvidenceCoverage] = []
    for supplier_name, group in sorted(identified.items()):
        ordered = sorted(group, key=lambda point: point.observation_id)
        source_urls = tuple(sorted({point.source_url for point in ordered}))
        suppliers.append(
            SupplierEvidenceCoverage(
                supplier_name=supplier_name,
                observation_ids=tuple(point.observation_id for point in ordered),
                source_urls=source_urls,
                offer_count=len(ordered),
                distinct_source_count=len(source_urls),
                moq_observation_count=sum(
                    point.minimum_order_quantity is not None for point in ordered
                ),
                incoterm_observation_count=sum(
                    point.incoterm is not None for point in ordered
                ),
                rankable_offer_count=sum(point.rankable for point in ordered),
                unknown_factors=tuple(
                    sorted(
                        {
                            factor
                            for point in ordered
                            for factor in point.unknown_factors
                        }
                    )
                ),
                due_diligence_status="UNVERIFIED",
            )
        )

    if not points:
        status = "NO_SUPPLIER_OBSERVATIONS"
    elif not suppliers:
        status = "NO_IDENTIFIED_SUPPLIERS"
    else:
        status = "SUPPLIER_EVIDENCE_COVERAGE"
    return SupplierCoverageSummary(
        status=status,
        suppliers=tuple(suppliers),
        unidentified_observation_ids=tuple(sorted(unidentified)),
        limitations=(
            "coverage describes retained offers and sources, not supplier identity proof",
            "distinct source URLs do not prove source independence",
            "supplier due diligence remains unverified without dedicated evidence",
            "country, capacity, certifications, payment terms, and legal status may be absent",
        ),
    )
