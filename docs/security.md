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

