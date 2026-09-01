# ADR 0008: Versioned opportunity workflow context

## Decision

Store optional `next_action`, timezone-aware `deadline`, and `notes` on the opportunity
aggregate. Expose a partial update endpoint that changes only explicitly supplied
fields and treats explicit JSON `null` as clearing a value. Every mutation locks the
tenant-owned row, requires its expected version, increments that same aggregate
version, and atomically appends an actor/correlation-attributed audit event.

The audit payload stores the sorted field names and resulting version, not the values.
This avoids duplicating commercially sensitive notes and actions into a broadly useful
audit ledger. The current opportunity row is the context source of truth; complete
historical note revisions are outside the MVP and would require a dedicated access and
retention policy.

`current_recommendation` is not manually editable in this change. Recommendations must
remain derived from evidence-backed research results rather than becoming unaudited
operator assertions.

## Consequences

- Status and context writers cannot silently overwrite each other from stale views.
- Clients can distinguish omitted fields from values intentionally cleared to null.
- Deadlines are rejected unless timezone-aware and normalized to UTC at persistence.
- Audit history proves what categories changed without becoming a copy of sensitive
  free-form text.
- Assignment, reminders, immutable note history, and derived recommendation projection
  remain future capabilities.
