# ADR 0007: Explicit opportunity lifecycle

## Decision

Represent opportunity progress as an explicit, server-enforced transition graph:

- `RESEARCHING` → `SOURCING`, `ON_HOLD`, or `LOST`
- `SOURCING` → `NEGOTIATING`, `EVALUATING`, `ON_HOLD`, or `LOST`
- `NEGOTIATING` → `EVALUATING`, `WON`, `LOST`, or `ON_HOLD`
- `EVALUATING` → `NEGOTIATING`, `WON`, `LOST`, or `ON_HOLD`
- `ON_HOLD` → any named active stage or `LOST`
- `WON` and `LOST` are terminal

Every transition requires an expected aggregate version. The repository locks the
tenant-owned row, checks that version and the graph, then commits the new status,
incremented version, and an actor/correlation-attributed audit event in one transaction.
Cross-tenant and missing identifiers share the same `404` behavior.

This graph is an initial conventional workflow assumption. It is not evidence of an
approved commercial process and must be reviewed with the product owner before the
feature is enabled in production. A later approved graph change should update this ADR
and its tests; it does not require rewriting historical audit events.

## Consequences

- Concurrent or stale clients cannot silently overwrite a newer lifecycle decision.
- Invalid skips, self-transitions, and terminal reopening fail explicitly.
- `ON_HOLD` does not infer a previous stage; clients must choose the resume target.
- Reopening a terminal result requires an explicit future policy or a new opportunity.
- No schema migration is needed because status and version already belong to the
  aggregate and audit events are append-only.
