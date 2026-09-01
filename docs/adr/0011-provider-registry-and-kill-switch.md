# ADR 0011: Typed provider registry and pre-network kill switch

## Decision

Maintain a typed registry of automated provider descriptors outside the HTTP layer.
Each descriptor states identity, category, enabled state, retrieval method, evidence
classification, terms-review status, supported scope, fixed hosts, cache policy,
declared rate limit, and explicit limitations. Expose the registry only through the
authenticated API.

Add a configuration kill switch for ECB and check it before invoking the lazy provider
service. The descriptor reports `PENDING_FORMAL_REVIEW`; this is deliberately not an
authorization claim. Because no verified upstream rate-limit contract is recorded, the
field is null rather than inferred.

## Consequences

- Operators and future UI code can inspect capabilities and governance status without
  reading source code or receiving credentials.
- Disabling ECB prevents adapter construction and network traffic immediately after a
  configuration restart/reload boundary.
- Production enablement still requires formal source authorization, egress approval,
  and monitoring; the development default does not override that gate.
- Each new automated source must add a descriptor, shutdown path, and contract tests.
- Runtime provider telemetry and dynamic configuration remain future work.
