# ADR 0021: Supplier evidence coverage without verification claims

## Decision

Create a run-level supplier evidence-coverage projection from immutable price
observations, ranking rows, and evidence URLs. Group only observations with the exact
same submitted supplier name. Preserve anonymous observations as individual IDs instead
of combining them into a fictional supplier.

For each identified supplier, expose ordered observation IDs and source URLs, offer and
distinct-URL counts, MOQ/Incoterm field counts, rankable-offer count, and the union of
ranking unknown factors. Set `due_diligence_status` to `UNVERIFIED` for every group.
Use the same pure calculation in the tenant-scoped API and new Persian reports.

Do not treat offer metadata as identity proof, distinct URLs as independent sources, or
ranking scores as supplier verification. Do not expose raw evidence through this view.

## Consequences

- Users can see exactly how much submitted commercial coverage exists per named
  supplier without parsing individual ranking records.
- Anonymous offers remain visible as data gaps and cannot accidentally reinforce each
  other under a shared placeholder identity.
- URL diversity is measurable but is explicitly weaker than source independence.
- Country, manufacturer/trader type, years active, certifications, capacity, payment
  behavior, reviews, and legal status require dedicated evidence and a future supplier-
  profile contract before verification can be represented.
