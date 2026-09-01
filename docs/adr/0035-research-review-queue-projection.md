# ADR 0035: Research review queue projection

## Decision

Expose a bounded tenant-scoped worklist for report-bearing research runs whose current
status is `NEEDS_VERIFICATION`, `NEEDS_HUMAN_REVIEW`, or `PARTIAL`. Support exact status
filtering and descending keyset pagination by immutable run creation time and ID.

Join only the required opportunity context, immutable report hash, validation
policy/result, and confidence columns. Batch-load validation severities and unknown counts
for the page and reuse the existing deterministic data-gap summary. Do not retrieve report
content, raw evidence, issue/unknown free text, opportunity notes, review rationale,
reviewer identity, or audit metadata. Return the current run version, but keep
approval/rejection in the existing locked review transaction.

Do not persist queue membership or emit audit events for a read. A review atomically moves
the run to `COMPLETED` or `CANCELLED`, which removes it from the projection without
deleting its immutable result or append-only review record.

## Consequences

- An API/UI consumer can discover review work without scanning every opportunity.
- Gap state remains policy-consistent with run and latest-decision projections.
- Pagination does not promise snapshot isolation when concurrent reviews remove items.
- Named users, role authorization, assignment, escalation, and service-level targets
  remain separate production hardening.
- No schema migration or new dependency is required.
