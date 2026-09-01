# ADR 0036: Minimal research review audit payload

## Decision

Keep the required normalized rationale in the tenant-scoped append-only research review
ledger. For new `REVIEW_RECORDED` audit events, record only the decision, previous and
resulting status, and resulting run version. Actor, tenant, aggregate, correlation, and
timestamp remain in the audit event envelope.

Do not duplicate rationale into the audit payload or the research review queue. The
authorized review-history endpoint remains the source for rationale. Apply this contract
only to newly written events; never update or delete historical audit rows that may use
the earlier payload shape. Audit consumers must tolerate both historical and current
payloads.

## Consequences

- Atomic review attribution and exact state/version history remain intact.
- Commercial free text has a narrower duplication and retention surface.
- Existing history remains append-only and reproducible.
- No schema migration or new dependency is required.
