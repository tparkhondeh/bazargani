# ADR 0038: Public review-audit projection

## Decision

Apply typed, action-specific payload allowlists when review audit events are projected
through the generic audit API. `REVIEW_RECORDED` exposes only a valid decision,
prior/resulting status, and resulting version. `IDENTITY_CLAIM_REVIEW_RECORDED` exposes
only bounded run/claim IDs, a valid decision, and prior/resulting versions. If an
allowlisted review payload does not validate, expose an empty payload rather than
passing untrusted values through or failing the whole audit page.

Perform this policy at response-model validation time. Always construct a new payload;
do not update the detached ORM record, database JSON, or historical audit row. Leave
non-review action payloads unchanged. Review-history endpoints, protected by the
matching reviewer role, remain the source for rationale.

## Consequences

- Historical research-review rationale is no longer exposed through the generic audit
  API even when it remains in immutable rows written under an earlier contract.
- Unexpected or invalid fields on either review action fail closed at the public
  boundary.
- Audit storage remains append-only and historical reproduction remains possible for
  authorized database governance processes.
- Consumers that previously read historical rationale from generic audit payloads must
  move to the role-authorized review-history endpoint.
- No schema migration or dependency change is required.
