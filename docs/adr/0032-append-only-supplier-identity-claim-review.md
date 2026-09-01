# ADR 0032: Append-only supplier identity claim review

## Decision

Record post-result review of an immutable, offer-scoped supplier identity claim in a
separate append-only ledger. Allow only `EVIDENCE_SUPPORTED`,
`EVIDENCE_CONTRADICTED`, and `INCONCLUSIVE`; these states describe whether the cited
evidence supports the submitted claim and must never be presented as verified supplier
identity or due diligence.

Require an authenticated tenant, credential actor fingerprint, bounded rationale, and
`expected_version`. Resolve the claim through its tenant-owned research run, lock that
claim row, compare the latest ledger version, and atomically append the review and a
minimal audit event. Return `404` for another tenant and `409` for a stale version. Keep
rationale in authorized review history but out of the audit payload.

Fold the latest ledger row into the live claim projection while preserving the complete
ordered history. Do not mutate the immutable evidence bundle, claim, validation result,
ranking, due-diligence coverage, or generated report. The report therefore remains the
ingestion-time `UNREVIEWED` snapshot. Restrict external claim IDs to bounded URL-safe
technical characters so every review resource has one unambiguous path.

## Consequences

- Conflicting or superseding human judgments remain visible instead of being overwritten.
- Optimistic concurrency prevents a stale reviewer from silently replacing a newer state.
- Evidence support can be triaged without creating a false `VERIFIED` supplier profile.
- API-key fingerprints provide credential attribution only; named users and role-based
  review authorization remain a production hardening requirement.
- Migration `20260901_0014` is additive and must pass parity, PostgreSQL constraints,
  backup, and full rollback/re-upgrade gates before deployment.
