# ADR 0013: Structured landed-cost calculation ledger

## Decision

Expose an authenticated, tenant-scoped read endpoint for each research run's persisted
landed-cost scenarios. Return optimistic, base, and conservative scenarios in semantic
order. Each scenario includes its quantity, target currency, total, per-unit amount,
and every calculated component's code, Persian label, amount, currency, evidence class,
and formula. Include scenario sensitivity through the existing shared calculation.

Keep product cost first, sort submitted named costs deterministically, and keep the
unexpected-cost contingency last. Return `404` when the run is outside the tenant or
has no calculated scenarios. Do not expose raw evidence bodies or create a mutation
path through this projection.

## Consequences

- API and UI consumers can inspect and reconcile decisions without parsing Markdown.
- The component sum can be checked against each immutable scenario total.
- Formula and evidence-class visibility make assumptions distinguishable from derived
  calculations, while source details remain available through bounded purpose-specific
  views.
- No schema migration is needed because the projection reads the existing scenario and
  component ledger.
- Historical rows are not rewritten; any future formula versioning must be captured at
  calculation time rather than inferred by this read model.
