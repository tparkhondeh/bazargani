# ADR 0034: Supplier identity review queue projection

## Decision

Expose a bounded tenant-scoped read projection for actionable supplier identity claim
reviews. Fold each immutable claim with the highest-version row in its append-only review
ledger and include only `UNREVIEWED` or `INCONCLUSIVE`. Support exact actionable-status
filtering and descending keyset pagination by immutable claim creation time and ID.

Join opportunity, offer, and source metadata needed for triage, but omit raw evidence,
review rationale, reviewer identity, and audit metadata. Preserve the existing claim
language: queue membership describes review work and never verified supplier identity.
Do not create a mutable queue table or write audit events for reads; resolved claims leave
the projection naturally while their complete review history remains available.

## Consequences

- Review work can be discovered across a tenant without scanning every research run.
- Latest-state folding remains deterministic and PostgreSQL/SQLite compatible.
- A concurrent review may change membership between pages; cursors order immutable
  claims but do not claim snapshot isolation across separate HTTP requests.
- Named users, role authorization, assignment, escalation, and service-level targets
  remain separate production-hardening work.
- No schema migration or new dependency is required.
