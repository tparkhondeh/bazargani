# ADR 0004 — Hashed API-key tenant boundary

Status: accepted as a bootstrap service-to-service control.

The FastAPI boundary resolves `X-API-Key` through configured SHA-256 digests to a
tenant and non-secret actor fingerprint. Application ports carry that principal
explicitly, repository aggregate access includes tenant predicates, idempotency is
tenant-scoped, and audit events record tenant and actor. Cross-tenant identifiers
return `404` to avoid existence disclosure. Production fails at startup without
authentication.

Raw keys are never stored by the application. Authentication may be disabled only
for local development. This decision does not claim end-user authorization is done:
OIDC/SSO, roles, managed rotation/revocation, distributed rate limits, and a secret
manager are required before public production use.
