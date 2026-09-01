# ADR 0037: API-key reviewer role boundary

## Decision

Extend the authenticated principal with roles configured by API-key SHA-256 digest.
Support two narrowly scoped roles: `RESEARCH_REVIEWER` and
`SUPPLIER_IDENTITY_REVIEWER`. Require the matching role for each review queue, review
history, and review write before invoking the repository. Return a generic
`403 AUTHORIZATION_DENIED` when the credential lacks the role, while preserving the
tenant-scoped `404` contract after successful role authorization.

Validate role configuration at startup: digest keys must identify configured
credentials, assignments must be non-empty, and role names must belong to the supported
set. Do not infer roles from tenant membership. Authentication-disabled development
receives both roles; production cannot use that mode.

## Consequences

- Review operations now fail closed for valid credentials without explicit grants.
- Separate credentials can receive only the review authority they need.
- Tenant isolation remains an independent repository boundary and does not become a
  role check.
- Roles authorize service credentials and do not prove named-human identity; OIDC/SSO
  and named-user policy remain production requirements.
- Existing deployments must configure digest-bound roles before review clients are
  upgraded; no schema migration or secret storage change is required.
