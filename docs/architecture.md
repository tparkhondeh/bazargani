# Architecture

## Decision

Use a Python modular monolith. Domain rules and calculation modules have no web,
database, scraper, or model dependencies. Application services orchestrate ports;
adapters implement acquisition, persistence, LLM, and delivery concerns.

```text
CLI / authenticated FastAPI / future RTL UI
                 |
        application services
        /        |         \
   domain   calculation   reporting
        \        |         /
        ports (provider/repository/model)
                 |
 adapters: HTTP/API/browser/database/LLM
```

## Module boundaries

- `domain`: immutable vocabulary, evidence, price, FX, research case.
- `calculation`: currency and landed-cost formulas only.
- `application`: use cases, deterministic quality validation/deduplication,
  explainable confidence, product matching, scenario sensitivity, and partial-result
  orchestration.
- `application/ranking`: deterministic offer comparison only; it never asserts
  supplier reliability without evidence and never compares incompatible units.
- `providers`: acquisition contracts and adapters; no business decisions.
- `reporting`: presentation from an already-computed result.
- `infrastructure`: SQLAlchemy/PostgreSQL repositories and tenant-scoped persistence.
  Queues and expanded telemetry remain future adapters.

## Options rejected for now

- Microservices: operational and consistency cost without independent scaling need.
- Agent framework as the core: hides deterministic state transitions and adds churn.
- Browser-first scraping: fragile, legally variable, difficult to secure and test.
- LLM-owned workflow/calculation: irreproducible and unsafe for financial decisions.

## Reliability

Research steps have explicit statuses and eventually persist checkpoints. Each
provider has timeout, bounded retry, rate-limit handling, caching, and an isolated
failure result. A run may complete partially with visible data gaps.

Liveness and readiness are separate public orchestration contracts. Liveness does not
depend on the database. Readiness verifies connectivity and, for Alembic-managed
environments, exactly one revision equal to the release's tested migration head. A CI
test keeps the embedded revision contract synchronized with the migration graph.

Result submission uses a scope-and-key idempotency ledger with a SHA-256 canonical
request hash. The immutable response snapshot and idempotency record commit in one
transaction. Same-key/same-hash retries replay the snapshot; same-key/different-hash
requests fail explicitly, including after a concurrent unique-key race.

The HTTP boundary buffers only bounded mutation bodies. It rejects a declared or
streamed body above the configured maximum before validation/use-case execution and
replays accepted chunks unchanged to FastAPI. Independent structural limits prevent a
small but combinatorially excessive evidence bundle from exhausting calculation or
database resources.

Request-schema errors pass through a bounded safe serializer rather than FastAPI's raw
validation representation. It retains only allowlisted location names, internal error
types, and generic messages; input values, context, and documentation URLs are omitted.
Application/parser code must opt into a specific client-visible reason with
`PublicInputError`, whose message is composed only from controlled labels and enums.
All other `ValueError` messages are treated as internal and replaced by a generic
input error at the HTTP boundary.

The outer response middleware applies no-store/no-cache, MIME sniffing, framing,
referrer, and browser-permission controls to success and error responses, including
body-limit rejections. Authenticated routes also vary on the API-key header as defense
in depth if an intermediary ignores `no-store`. Transport security remains an edge
responsibility because the app does not trust arbitrary forwarded-protocol headers.

That same outer boundary catches otherwise unhandled exceptions after lower layers
have rolled back/closed their contexts. It emits a generic correlated `500` and logs
only exception type and request metadata, ensuring unexpected errors cannot bypass the
normal correlation or security-header pipeline.

The API authenticates a secret key at the boundary, resolves it to an immutable
tenant/actor principal, and passes that principal explicitly through application
ports. Aggregate reads and writes include tenant predicates; an identifier owned by
another tenant is deliberately indistinguishable from a missing identifier (`404`).
Health/readiness remain public and expose no tenant data.

After authentication, the HTTP boundary applies a thread-safe fixed-window budget by
resolved tenant rather than raw credential. This prevents multiple or rotating keys
from multiplying the in-process allowance. The limiter deliberately has no database
dependency; it is a single-process defense and does not replace a shared edge limiter.

System-derived research outcomes and operator actions use separate paths. The generic
transition route permits only operational lifecycle changes; a review-required result
can reach `COMPLETED` or `CANCELLED` only through an append-only review decision. The
review row, locked run version update, and audit event share one transaction.

Opportunity lifecycle mutations also lock the tenant-owned aggregate and compare an
explicit expected version before applying the state-machine rule. The status/version
update and audit row share one transaction, preventing a successful state change
without history. Terminal outcomes require a new aggregate rather than an implicit
reopen; the initial commercial transition graph remains a stakeholder-validation item.

Mutable opportunity context uses the same aggregate version as lifecycle status, so a
client cannot update a note or deadline using a stale view of the stage. PATCH applies
only explicitly supplied fields and supports explicit null clearing. Audit records the
changed field names and resulting version but deliberately avoids duplicating sensitive
commercial text; this is a change ledger, not a full historical snapshot store.

The opportunity decision view is assembled at read time from the newest tenant-owned
research run joined to an immutable report. Validation, scenario summaries, and all
rank-1 rows belong to that same run, avoiding a denormalized recommendation that could
drift from evidence. Empty newer runs are skipped. The projection preserves rank ties
and leaves report content unmodified; any future HTML UI must render it with a strict
sanitization policy.

Scenario sensitivity is a pure application calculation over the three immutable
landed-cost summaries. The same function feeds report generation and the read-time
latest-decision projection, preventing presentation-specific formulas from drifting.
It fails closed to `MIXED_BASIS` when quantities or target currencies differ and never
fills missing comparison values with estimates.

The run-level landed-cost ledger is assembled from tenant-owned persisted scenario and
component rows. Scenario ordering is optimistic/base/conservative; component ordering
keeps product cost first, named costs deterministic, and contingency last. The JSON
view exposes formulas and evidence classes for auditability, omits raw evidence bodies,
and derives sensitivity through the shared application function.

Supplier-offer read models join the immutable ranking row to its exact price
observation, evidence row, and source. This prevents clients from treating a detached
score as a decision and keeps normalized and original values visible together. The
summary omits raw evidence content while retaining the URL, retrieval metadata, class,
confidence, and transformation needed for provenance-aware display.

Report generation treats every domain/input string as untrusted presentation data.
Plain text is collapsed to one line, HTML-encoded, and Markdown-escaped; code spans use
a fence longer than any embedded backtick; HTTP(S) link targets are percent-encoded.
This prevents input from changing document structure while preserving provenance.
Persisted report snapshots and hashes are immutable, so this policy applies to newly
generated reports rather than rewriting history.

History traversal uses deterministic `(timestamp, id)` descending keyset pagination,
not unbounded reads or offset drift. Opportunities/runs use creation time and audit
events use occurrence time. The URL-safe cursor is validated into UTC time and a UUID,
while tenant ownership remains an independent repository predicate.

Opportunity history can add an exact lifecycle-status predicate before applying the
same `(created_at, id)` keyset boundary. The query matches the existing tenant/status/
creation index; cursors retain ordering state only and never carry filter authority.

The ECB reference-rate application service constructs its HTTP adapter lazily and
caches successful currency results for a bounded TTL. Cache misses are serialized to
avoid an upstream request stampede. Adapter network, response-size, and format errors
become a stable upstream-unavailable error; failed fetches and stale values are not
cached or relabelled as current facts.

Provider governance metadata lives in a typed provider registry outside the HTTP
layer. It exposes only controlled operational facts and explicit unknowns. The ECB kill
switch is checked before lazy provider construction, so disabling it cannot trigger a
network request; adding a provider requires a new descriptor rather than ad-hoc API
metadata.

## Configuration

Development, test, and production use environment-specific configuration validated
at startup. Secrets come from environment/secret managers and are redacted from
structured logs. No environment-specific business rules belong in source code.
