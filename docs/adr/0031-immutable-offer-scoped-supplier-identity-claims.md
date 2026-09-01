# ADR 0031: Immutable offer-scoped supplier identity claims

## Decision

Accept optional supplier legal-identity claims only inside the immutable evidence
bundle and persist them in the same result transaction. Require a bounded external claim
ID, exact price-observation ID, claimed legal name, jurisdiction, registration number,
and full evidence. Reuse evidence fingerprinting and source lineage, while storing the
claim in its own migration-backed table.

Keep claims scoped to one offer. Never overwrite the quoted supplier name, merge equal
names across offers or runs, create a supplier profile, remove ranking unknowns, change
scores, or promote due diligence. Exclude a claim whose observation is removed by
deterministic duplicate handling and emit an explicit validation error rather than
reattaching it.

Expose a tenant-scoped summary shared with the report. Every v0.46 claim has the fixed
status `UNREVIEWED`, even when its submitted evidence is labelled `FACT`/`HIGH`. Omit raw
evidence bodies from reads and escape all claim/source fields as untrusted content.
Implement review decisions later as a separate append-only ledger; do not add evidence
after completion and mutate the original result snapshot.

## Consequences

- Source assertions about legal identity are preserved without being presented as
  verified supplier facts.
- Evidence catalog and freshness projections account for identity-claim usage while raw
  source content remains available only inside protected persistence.
- Multiple evidence sources may assert the same identity through distinct claim IDs;
  source count is not treated as independence or truth.
- Existing offers and idempotency payloads remain compatible with a zero claim count.
- Migration `20260901_0013` is additive and must pass backup, parity, PostgreSQL, and
  rollback/re-upgrade gates before deployment.
