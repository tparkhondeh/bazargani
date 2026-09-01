# Bazargani Trade Intelligence Agent

An evidence-first vertical slice for turning a product sourcing request into a
reproducible landed-cost decision report.

## Current slice

The first slice accepts a JSON research case containing the user's request,
source-backed price observations with explicit units, point-in-time FX rates, and
explicit cost assumptions. It validates provenance and freshness, removes exact
duplicates, flags conflicts and price outliers, calculates optimistic/base/
conservative landed-cost scenarios with `Decimal`, and emits a Persian Markdown
report with an explainable confidence score. Each retained price is also classified
as an exact product, exact variant, comparable, similar, or substitute using a
policy-versioned deterministic feature ledger.
It also ranks actionable supplier offers within comparable unit/currency groups using
quantity fit, MOQ, product match, evidence quality, commercial completeness, and
normalized price—while keeping supplier due diligence explicitly unresolved.
The decision view and new reports also expose exact per-unit deltas and percentage
sensitivity around the base scenario. Comparison is withheld when scenario quantities
or currencies differ, and the output explicitly does not claim to be an EOQ model.

It intentionally does **not** invent prices or scrape arbitrary URLs. Phase 2 adds
the first PostgreSQL/Alembic persistence boundary, audited research-run state machine,
and FastAPI endpoints. Automated source adapters and the RTL web UI remain phased work
documented in `docs/roadmap.md`.

## Run locally

Python 3.12+ is required.

```powershell
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
```

```powershell
python -m trade_agent.cli examples/demo_case.json --output reports/demo.md
```

When running from a source checkout without installing the package:

```powershell
$env:PYTHONPATH = "src"
python -m trade_agent.cli examples/demo_case.json --output reports/demo.md
```

The example is explicitly labelled `DEMO` and must never be treated as market
data.

## Quality gates

```powershell
python -m unittest discover -s tests
python -m ruff check .
python -m mypy
python -m compileall -q src tests
python -m pip check
python -m pip_audit -r requirements.lock --strict --progress-spinner off
```

The advisory audit requires network access and fails the local/CI gate when a known
vulnerability is reported for the exact locked environment.

See `docs/` for specification, architecture, security, data model, source
strategy, open-source evaluation, testing strategy, and roadmap.

## API foundation

Phase 2 adds PostgreSQL/Alembic persistence and a FastAPI service. See
`docs/operations.md` for local commands. Initial endpoints are:

- `GET /health` and `GET /ready`
- `POST /api/v1/requests/parse`
- `GET /api/v1/providers`
- `GET /api/v1/reference-rates/ecb/{quote_currency}`
- `GET /api/v1/audit-events`
- `POST /api/v1/opportunities`
- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `POST /api/v1/opportunities/{id}/transitions`
- `PATCH /api/v1/opportunities/{id}/context`
- `GET /api/v1/opportunities/{id}/latest-decision`
- `POST /api/v1/opportunities/{id}/research-runs`
- `GET /api/v1/opportunities/{id}/research-runs`
- `POST /api/v1/research-runs/{id}/transitions`
- `POST /api/v1/research-runs/{id}/reviews`
- `GET /api/v1/research-runs/{id}/reviews`
- `POST /api/v1/research-runs/{id}/evidence-bundle`
- `GET /api/v1/research-runs/{id}/report`
- `GET /api/v1/research-runs/{id}/validation`
- `GET /api/v1/research-runs/{id}/product-matches`
- `GET /api/v1/research-runs/{id}/supplier-offer-rankings`

`/health` and `/ready` are public for orchestration. Health reports process liveness;
readiness checks database connectivity and, when Alembic manages the schema, requires
the exact migration head shipped with the release. Missing/stale schema returns a
stable `503 NOT_READY`. Every `/api/v1` endpoint is authenticated when
`TRADE_AGENT_AUTH_ENABLED=true` and requires `X-API-Key`. Only SHA-256 key digests are
configured; the resolved tenant and a non-secret key fingerprint are propagated into
tenant-scoped repository queries and audit events. Production configuration fails at
startup if authentication is disabled.

Authenticated API traffic has a per-tenant, per-process fixed-window limit (default
120 requests per 60 seconds). Every key mapped to a tenant shares its budget;
exhaustion returns `429 RATE_LIMIT_EXCEEDED` with `Retry-After`. Health/readiness are
excluded. A trusted edge/distributed limiter is still required for production because
budgets multiply across workers and reset with the process.

Opportunity lifecycle changes use an explicit state machine and require the current
aggregate version. The locked status/version update and actor-attributed audit event
commit atomically. `WON` and `LOST` are terminal; `ON_HOLD` can resume only through a
named target stage. The initial transition policy is documented in ADR 0007 and must
be validated with commercial stakeholders before production use.

The opportunity context endpoint partially updates `next_action`, timezone-aware
`deadline`, and `notes` under the same row-lock and expected-version boundary. Values
can be explicitly cleared with JSON `null`. The audit event records only field names
and the resulting version so commercial note content is not duplicated into the audit
ledger.

The latest-decision projection returns the newest research run under an opportunity
that actually has an immutable report, together with validation, the three landed-cost
summaries, and every rank-1 offer (including ties). A newer empty/in-progress run does
not erase the last evidence-backed decision, and the endpoint never chooses one tied
supplier arbitrarily. It derives scenario sensitivity at read time using `Decimal`;
mixed quantity/currency bases return `MIXED_BASIS` without comparison numbers.

Supplier ranking responses are evidence-backed offer views: they include the original
price/currency, quoted quantity, unit, MOQ, Incoterm, source identity/URL, retrieval
time, evidence class/confidence, and transformation beside the deterministic score.
Raw evidence bodies are not duplicated into these decision summaries.

Statuses derived from validation cannot be manually promoted to `COMPLETED` through
the generic transition endpoint. An authenticated actor must record an `APPROVE` or
`REJECT` review with a rationale and expected version. The decision, status/version
change, actor fingerprint, and audit event commit atomically; cross-tenant review
access returns `404`. API-key attribution is a service baseline, not proof of a named
human identity—OIDC/roles remain required for production user accountability.

Opportunity, research-run, and audit-event history endpoints use newest-first opaque
cursor pagination. `limit` is bounded to 1–100 (default 50); `next_cursor` is returned
only when another page exists. Cursors encode ordering state, not authorization: every
query independently applies the authenticated tenant predicate and malformed or
oversized cursors fail with `422`. Audit responses expose the non-secret actor
fingerprint, correlation/aggregate metadata, action, timestamp, and structured event
payload, but omit `tenant_id`.

Opportunity history accepts an optional exact `status` enum filter. Filtering remains
inside the tenant-scoped indexed query and works with the same bounded cursor contract;
an invalid status fails schema validation instead of being silently ignored.

The authenticated ECB reference-rate endpoint exposes the latest supported EUR quote
with its official source URL, retrieval/effective times, raw observation, confidence,
and explicit informational rate type. A bounded in-process cache (default one hour)
reduces upstream load. Upstream/network/format failure returns a stable `502` and is
never replaced by silently stale or invented data.

The authenticated provider registry exposes machine-readable scope, fixed hosts,
cache policy, limitations, enabled state, and terms-review status. ECB can be disabled
immediately with `TRADE_AGENT_ECB_ENABLED=false`; disabled calls fail before constructing
or contacting the provider. Formal terms review remains pending and no undocumented
upstream rate-limit number is asserted.

The evidence-bundle endpoint requires a version-matched `RUNNING` research run. It
calculates and persists evidence, price observations, point-in-time FX, all three
landed-cost scenarios, validation summary/issues, assumptions/unknowns, an immutable
report snapshot, and an audit event in one transaction. A result with warnings is
marked `NEEDS_VERIFICATION`; material conflicts are marked `NEEDS_HUMAN_REVIEW`
instead of being silently reported as complete.

New Markdown reports encode all untrusted names, labels, notes, identifiers, and source
metadata before interpolation. Input newlines cannot create headings, HTML tags remain
text, Markdown control characters are escaped, and link targets are percent-encoded.
Previously persisted reports remain immutable; browser clients must still render every
report with an HTML-disabled or strictly sanitized Markdown policy.

Every evidence-bundle submission also requires an `Idempotency-Key` header containing
1–128 URL-safe identifier characters. An exact retry returns the original immutable
completion with `idempotency_replayed=true`; reusing the key for a different run body
returns `409 IDEMPOTENCY_CONFLICT`. The idempotency record is committed in the same
transaction as the research result.

Mutating HTTP requests are capped at 2,000,000 bytes by default, including chunked
requests without `Content-Length`; oversized requests receive `413 REQUEST_TOO_LARGE`.
The evidence parser also caps observations (500), FX rates (100), scenarios (3),
costs per scenario (100), notes per kind (200), and product attributes (100).

Schema-validation failures return `422 REQUEST_VALIDATION_FAILED` with at most 50
safe details containing an allowlisted field location, validation type, and generic
message. Raw input, Pydantic context, and error URLs are never reflected; additional
errors are represented by an explicit omission marker.

Domain/parser failures use `422 INVALID_INPUT`. Only deliberately authored
`PublicInputError` messages may provide a specific safe reason; every other
`ValueError` is reduced to `request input is invalid`, so identifiers embedded in
invariant failures are not reflected to clients.

Every HTTP response uses `Cache-Control: no-store`, `Pragma: no-cache`,
`X-Content-Type-Options: nosniff`, deny framing/referrers, and disables browser device
permissions. `/api/v1` responses also vary on `X-API-Key`. HSTS belongs at the trusted
TLS edge and is not inferred from client-controlled forwarding headers.

Unexpected application/provider/database exceptions return a stable
`500 INTERNAL_ERROR` with the correlation ID and the same response-security headers.
Exception messages and classes are not exposed to clients; structured logs record only
the exception class plus method, path, and correlation—not the exception text.
