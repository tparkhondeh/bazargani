# ADR 0016: Metadata-only evidence catalog

## Decision

Expose an authenticated, tenant-scoped evidence catalog for each research run. Return
every deduplicated evidence record once with its source name/URL, retrieval time,
classification, confidence, transformation, record ID, and stored SHA-256 fingerprint.

Attach deterministic usage references without duplicating evidence: price usages name
the external observation ID; FX usages identify scenario, currency pair, rate type, and
effective time. Sort records and usages deterministically.

Do not return `raw_value` from this decision-oriented endpoint. A content fingerprint
helps consumers compare integrity and lineage but is not a quality, authenticity, or
trust claim. Any future raw-evidence retrieval requires a separate authorization,
retention, and audit policy.

## Consequences

- Clients can explain which evidence supports which price and FX input without joining
  internal database tables or parsing reports.
- Shared evidence remains one catalog item even when several scenarios consume it.
- Raw captured content is not broadly redistributed through normal result reads.
- Cross-tenant access remains indistinguishable from a missing run.
- Evidence for future component types must add an explicit usage kind and contract test.
