from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    id: str
    name: str
    category: str
    enabled: bool
    retrieval_method: str
    evidence_classification: str
    terms_review_status: str
    terms_approved: bool
    supported_scope: tuple[str, ...]
    fixed_hosts: tuple[str, ...]
    cache_ttl_seconds: int
    declared_rate_limit: str | None
    limitations: tuple[str, ...]


def provider_catalog(
    *,
    ecb_enabled: bool,
    ecb_terms_approved: bool,
    ecb_cache_ttl_seconds: int,
) -> tuple[ProviderDescriptor, ...]:
    return (
        ProviderDescriptor(
            id="ecb-fx-reference",
            name="European Central Bank Data Portal",
            category="FX_REFERENCE",
            enabled=ecb_enabled,
            retrieval_method="OFFICIAL_API",
            evidence_classification="FACT",
            terms_review_status=(
                "APPROVED" if ecb_terms_approved else "PENDING_FORMAL_REVIEW"
            ),
            terms_approved=ecb_terms_approved,
            supported_scope=("EUR daily reference exchange rates",),
            fixed_hosts=("data-api.ecb.europa.eu",),
            cache_ttl_seconds=ecb_cache_ttl_seconds,
            declared_rate_limit=None,
            limitations=(
                "informational reference rate; not an executable dealer quote",
                "not an Iranian remittance, settlement, sanctions, or customs rate",
                "production egress requires documented terms approval and network review",
            ),
        ),
    )
