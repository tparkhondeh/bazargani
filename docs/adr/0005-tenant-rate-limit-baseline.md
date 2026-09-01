# ADR 0005: Tenant-aware API rate-limit baseline

## Decision

Apply a thread-safe fixed-window limit to every authenticated `/api/v1` request after
the API key resolves to a tenant. All keys mapped to the same tenant share the same
per-process budget. Public health/readiness endpoints are excluded. Exceeding the
budget returns a stable `429 RATE_LIMIT_EXCEEDED` response with `Retry-After`.

The default is 120 requests per 60 seconds per tenant per process. Both values are
bounded configuration. A reverse proxy or shared distributed limiter remains
mandatory before multi-worker or public production exposure.

## Consequences

- Key rotation cannot multiply a tenant's application-level budget.
- The limiter has no database/network dependency and can fail neither persistence nor
  evidence transactions.
- Budgets reset on process restart and multiply across workers/instances, so this is
  defense in depth rather than the production distributed control.
- Invalid credentials are rejected before tenant limiting; edge controls must limit
  unauthenticated abuse without trusting spoofable forwarding headers in the app.

## Rejected alternatives

- Raw-key buckets allow rotation or multiple keys to bypass a tenant budget.
- Application IP buckets are unreliable behind proxies and risk trusting spoofed
  forwarding headers; source-IP policy belongs at the trusted reverse-proxy edge.
- A database-backed counter adds contention and availability coupling without
  providing a purpose-built distributed rate-limit primitive.
