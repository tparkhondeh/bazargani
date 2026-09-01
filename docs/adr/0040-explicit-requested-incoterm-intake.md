# ADR 0040: Explicit requested-Incoterm intake

## Decision

Recognize a requested Incoterm code only inside a clause marked by `Incoterm`,
`Incoterms`, `delivery term`, «اینکوترمز», or «شرط تحویل». Reuse the shared ordered
Incoterms 2020 code tuple as a finite recognition vocabulary, uppercase matches, and
deduplicate them case-insensitively in source order.

Return one distinct recognized code as `requested_incoterm_code`. If a marked clause has
multiple distinct codes, clear the selected value, expose the codes through
`field_conflicts`, and require clarification. If a marker has no recognized code,
require clarification without promoting the unsupported value into a structured code
or conflict candidate. Ignore standalone code-like text outside a marked clause so
product names are not reclassified.

Treat this field only as deterministic intake of a user preference. Do not infer an
Incoterms version or named place, do not write an offer term, and do not alter validation,
ranking, landed-cost scenarios, or reports. Preserve the original request text for later
clarification; structured evidence remains the only path into commercial result data.

## Consequences

- A common commercial constraint becomes machine-readable without an LLM or external
  service.
- Conflicting or unsupported clauses fail closed into a question instead of a guessed
  constraint.
- Using the 2020 vocabulary for recognition does not claim that the user declared the
  2020 version.
- `requested_incoterm_code` and its confidence entry are additive API fields; the
  existing `field_conflicts` structure carries multiple recognized codes.
- Named-place/version intake and other commercial constraints remain future work; no
  database migration or dependency change is required.
