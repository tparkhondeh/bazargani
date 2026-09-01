# Security and Initial Threat Model

## Assets

Provider credentials, supplier/contact data, commercial prices, research history,
user identity, reports, and production infrastructure.

## Primary threats and controls

- **SSRF/DNS rebinding:** adapters accept only HTTPS public destinations, resolve and
  reject private/link-local/loopback/reserved IP ranges, block redirects to denied
  ranges, deny user-controlled proxies, and enforce egress at the network layer.
- **Prompt/content injection:** retrieved content is untrusted data; it cannot grant
  permissions, select tools, disclose secrets, or alter system rules.
- **Credential leakage:** environment/secret manager only, redacted structured logs,
  least privilege, rotation, and no credentials in browser payloads.
- **Injection and unsafe output:** parameterized persistence, schema validation,
  output encoding, bounded inputs, and safe report rendering.
- **Abusive acquisition:** per-provider allowlists, terms review, rate limits,
  robots/policy compliance, timeouts, caching, and a kill switch.
- **Supply chain:** pinned lockfile once dependencies enter, automated advisory scan,
  license inventory, reviewed upgrades, and isolated build credentials.
- **Unauthorized actions:** authentication/authorization at the API boundary,
  tenant-aware repositories, auditable state transitions, and human approval before
  external communication or purchasing.

## Authentication and tenant boundary

The current service-to-service baseline accepts `X-API-Key` only on `/api/v1`.
Configuration stores SHA-256 digests mapped to stable tenant identifiers; raw keys
are neither stored in the database nor written to application logs. Comparison uses
constant-time digest matching, and audit rows contain the tenant plus a short,
non-secret digest fingerprint as actor identity.

Every aggregate lookup is tenant-scoped. Cross-tenant reads and mutations return the
same `404` contract as nonexistent records to avoid confirming identifiers. Research
result idempotency scopes also include the tenant. Production settings fail closed
unless authentication is enabled with at least one valid hashed credential.

Disabling authentication is a local-development convenience only and maps requests
to `local-development`; it is rejected in production. API keys are a bootstrap
control, not the final user authorization model: OIDC/SSO, roles, key rotation,
revocation, distributed rate limits, and secret-manager delivery remain required
before public production exposure.

Production is blocked until TLS, reverse proxy policy, secret storage, backup restore,
logging retention, authorization roles, and server reconciliation are verified.

Evidence-bundle mutations require bounded, URL-safe idempotency keys. Keys are scoped
to a research run and bound to a canonical SHA-256 request hash; a key cannot be used
to substitute a different payload. Keys and hashes are operational metadata, never
authorization credentials.

POST/PUT/PATCH bodies are bounded before JSON parsing, even when `Content-Length` is
missing. The default application limit is 2 MB and the reverse proxy must enforce an
equal or smaller limit in production. Evidence collections have separate item-count
caps. A `413` response preserves the correlation ID but never echoes request content.
