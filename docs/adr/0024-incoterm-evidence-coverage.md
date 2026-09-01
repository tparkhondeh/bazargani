# ADR 0024: Incoterm evidence coverage before scenario comparison

## Decision

Create a pure run-level projection over submitted price observations. Normalize each
non-empty Incoterm declaration to uppercase, compare it with one shared Incoterms 2020
reference-code vocabulary, and group offers deterministically by code. Expose exact
observation IDs, named suppliers, source URLs, counts, unrecognized declarations, and
observations with no declaration through the tenant-scoped API and Persian report.

Keep `WITHHELD_NO_INCOTERM_SCENARIOS` as a separate comparison status for every result.
Do not select or rank a code because the current model does not capture a structured
named place, asserted edition, route-specific cost allocation, operational control, or
risk-transfer scenarios. Treat distinct URLs only as coverage, not independent proof.

## Consequences

- Users can audit which Incoterm codes were actually declared without mistaking field
  presence for contract verification.
- Validation and coverage share one reference vocabulary, preventing code-list drift.
- Unknown and missing declarations remain visible instead of being silently coerced.
- A future comparison feature requires explicit schema and evidence for named places,
  route alternatives, cost ownership, control, risk transfer, and legal review.
