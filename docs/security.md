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
