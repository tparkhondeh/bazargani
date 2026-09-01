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
- **Supply chain:** exact reviewed lockfile, blocking automated advisory scan against
  that lock, direct-dependency license inventory, reviewed upgrades, pinned CI actions
  and service images, and isolated build credentials.
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

Every authenticated `/api/v1` request consumes a fixed-window budget keyed by the
resolved tenant, so multiple active credentials for rotation share the same allowance.
The default is 120 requests per 60 seconds per process. Exhaustion returns `429` with
`Retry-After` and does not expose the tenant identifier. Health/readiness remain
public; invalid-key and multi-worker abuse require rate controls at the trusted edge.

Review decisions require a non-empty rationale and optimistic version, lock the
tenant-owned run, and atomically record the actor, decision, before/after state, and
audit event. The generic status endpoint cannot mark a run completed or fabricate a
validation/review status. The current actor is a non-secret API-key fingerprint; it
must not be represented as verified human identity until OIDC and roles are enabled.

Opportunity transitions use the same tenant predicate, row lock, optimistic version,
and atomic audit boundary. Invalid stage changes return `409`, stale writers cannot
overwrite newer decisions, and cross-tenant identifiers remain indistinguishable from
missing records. `WON` and `LOST` cannot be reopened through this API.

Opportunity notes, next actions, and deadlines share the tenant/version/row-lock
boundary. Audit events contain only changed field names and the resulting version, not
the field values, reducing duplication of commercially sensitive text. Authorized
clients can still read the current values, so future named-user roles and retention
policy remain production requirements.

Latest-decision reads first establish tenant ownership and select report, validation,
scenarios, and offer rankings only through that tenant-owned run. The response exposes
no tenant identifier. Report Markdown and source-linked content remain untrusted data;
a future browser renderer must sanitize/encode them and must not execute embedded HTML.

Evidence-backed offer summaries expose authorized commercial price context and public
source URLs, but deliberately omit stored `raw_value` bodies. Tenant ownership is
established through the parent run before all joins. URLs and source names remain
untrusted display data and cannot be used as fetch/tool instructions by clients.
Payment text, payment method, quote-validity time, and lead-time values inherit the same
tenant and evidence boundary. Their presence is not supplier verification or purchasing
authorization, and text remains untrusted presentation data for report/UI encoding.

Supplier identity claims remain inside the tenant-owned research-run boundary. Reads
first authorize the run, then independently constrain claim, offer, and evidence joins
to that same run. API/report views omit raw evidence bodies and escape legal names,
jurisdictions, registration numbers, source labels, and URLs as untrusted content. A
submitted `FACT`/`HIGH` label is preserved but cannot change offer ranking or supplier
due-diligence result. Claim IDs used in review paths accept only a bounded technical
ASCII identifier and cannot contain `/` or path-control characters.

Identity-claim review reads and writes independently re-establish the tenant boundary
through the parent run and return `404` across tenants. Writes lock the claim and require
the current ledger version; prior review rows are never updated. The decision vocabulary
contains no `VERIFIED` state. Review rationale is visible only through the authenticated
tenant-scoped history and is not copied into the audit payload or immutable report. The
API-key actor fingerprint is attribution to a credential, not proof of a named reviewer;
production identity/role controls remain required.

The Markdown generator encodes HTML and escapes Markdown control characters in all
untrusted text, flattens embedded newlines, uses adaptive code fences, and percent-
encodes provenance link targets. This is defense in depth, not permission to enable raw
HTML in a client renderer: UI policy must still disable HTML or apply an allowlist
sanitizer and safe external-link attributes.

History cursors are bounded opaque ordering tokens, not bearer credentials. Decoding
requires an exact schema, timezone-aware timestamp, and UUID. A valid cursor from any
source can only reposition an already tenant-scoped query and cannot grant access.
Status filtering is applied as an additional enum predicate within that query; it
cannot weaken tenant ownership and unrecognized status text is rejected.

Audit history is read only through a bounded tenant-scoped query. The response omits
`tenant_id` and never contains raw API keys; actor attribution remains the non-secret
key fingerprint. Audit payload design must continue to exclude credentials and raw
evidence bodies, while review rationale remains visible to authorized tenant clients.

The ECB adapter remains fixed to one HTTPS host, rejects redirects and non-public DNS
results, ignores environment proxies, bounds response bytes, and retries transport or
server failures. The API requires authentication to limit anonymous abuse. Only
successful parsed observations enter the TTL cache; a provider failure returns `502`
without serving a stale value as if it were current.

The authenticated provider registry exposes scope and fixed-host policy without
credentials. ECB has a configuration kill switch checked before adapter construction;
disabled requests cannot reach the network. Production startup rejects enabled ECB
configuration unless `TRADE_AGENT_ECB_TERMS_APPROVED=true`; the registry reports the
same boolean and derives `APPROVED`/`PENDING_FORMAL_REVIEW` from it. The flag is an
operator assertion backed by a separately retained authorization decision, not legal
evidence by itself. Network egress allowlisting and review remain independent controls,
and an undocumented upstream rate limit remains explicit null.

Provider runtime health is authenticated and passive: reading it cannot construct the
adapter or trigger network traffic. It exposes bounded process-local counters and UTC
timestamps, never exception text, URLs, response bodies, credentials, or commercial
values. Invalid client input is rejected before an upstream attempt is counted. Health
state resets on restart and records only the last observed request-driven attempt, so it
must not be treated as a cross-worker control, current reachability proof, or SLA.

`pip-audit` checks the exact Python lock in every CI run and fails on known published
advisories. The lock and `THIRD_PARTY_NOTICES.md` are reviewed together whenever a
dependency changes. A clean advisory result is point-in-time evidence, not a guarantee
that a dependency is defect-free; repeat the gate for every change and release.

Production is blocked until TLS, reverse proxy policy, secret storage, backup restore,
logging retention, authorization roles, and server reconciliation are verified.

The public readiness response reveals only the expected migration revision after a
successful check. Connectivity failures, missing metadata tables, stale/multiple
revision states, and database driver details collapse to `503 NOT_READY`; liveness
stays independent so a database outage does not cause a process restart loop.

Evidence-bundle mutations require bounded, URL-safe idempotency keys. Keys are scoped
to a research run and bound to a canonical SHA-256 request hash; a key cannot be used
to substitute a different payload. Keys and hashes are operational metadata, never
authorization credentials.

Successor-run creation independently scopes idempotency to tenant and source run, locks
and authorizes the source, checks its version, and requires an existing immutable report.
Cross-tenant calls return `404`. The normalized recalculation reason is visible in
authorized run history but is not duplicated into audit payloads; audit records only
predecessor ID and source version. Successors copy no raw evidence, report, or calculated
row, preventing stale historical values from silently becoming current inputs.

The supplier identity review queue applies the tenant predicate through the owning
research run before returning any claim. It exposes the same bounded claim and source
metadata already available to an authorized tenant, but omits raw evidence, review
rationale, reviewer actor identity, and audit metadata. Collection reads return an empty
page rather than revealing whether another tenant has matching review work.

POST/PUT/PATCH bodies are bounded before JSON parsing, even when `Content-Length` is
missing. The default application limit is 2 MB and the reverse proxy must enforce an
equal or smaller limit in production. Evidence collections have separate item-count
caps. A `413` response preserves the correlation ID but never echoes request content.

Pydantic/FastAPI validation exceptions are never stringified into responses because
their raw representation may include rejected input and context. The public `422`
contract emits at most 50 allowlisted locations and internal validation types with
generic messages, then an omission marker; unknown location names are replaced with
`field` and raw input, context, and error URLs are discarded.

Domain/parser `ValueError` text is also non-public by default because invariant
messages can contain cost codes, observation identifiers, currencies, or other input.
Only explicitly reviewed `PublicInputError` messages built from controlled labels may
cross the API boundary; all other values collapse to a generic `INVALID_INPUT` reason.

All application responses disable storage and legacy caching, MIME sniffing, framing,
referrers, camera, microphone, and geolocation. Tenant API responses also include
`Vary: X-API-Key`. HSTS is deliberately not emitted by the loopback-capable app: the
trusted TLS edge must set it after domain/TLS verification, without trusting arbitrary
forwarded headers from clients.

Unhandled exceptions are caught at the outer request boundary so they cannot skip
correlation or response hardening. The client receives only `INTERNAL_ERROR` and a
correlation ID. Structured logging records the exception class, method, and path but
deliberately omits exception text/trace and request data, which may contain credentials,
DSNs, SQL parameters, provider URLs, or commercial values.
