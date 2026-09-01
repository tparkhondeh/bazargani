# ADR 0015: Immutable assumption and unknown read model

## Decision

Expose the persisted `ASSUMPTION` and `UNKNOWN` note collections through an
authenticated, tenant-scoped research-run endpoint and include the same collections in
the evidence-backed latest-opportunity decision. Return deterministic text ordering;
do not require clients to parse the Markdown report.

Require every submitted note to be a non-empty string no longer than 5,000 characters,
with the existing 200-item limit per kind. Strip surrounding whitespace before the
research result is calculated and persisted.

Keep completed research runs immutable. This read model does not introduce a PATCH
operation: correcting an assumption must create a successor run and explicitly
recalculate dependent results in a future workflow.

## Consequences

- Result clients can clearly distinguish declared assumptions from unresolved unknowns.
- Structured output remains traceable to the same run/report/scenario snapshot.
- Malformed nested values and oversized note payloads cannot become unbounded report or
  database content.
- Opportunity workflow notes remain a separate mutable concern with value-redacted
  audit metadata.
- Successor-run lineage and selective dependency recalculation remain future work.
