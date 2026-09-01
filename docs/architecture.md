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

Explicit recalculation creates a new empty research-run aggregate with a self-referencing
predecessor ID and bounded reason. The application layer canonicalizes and hashes the
source ID, source version, and normalized reason. The repository checks idempotency,
locks the tenant-owned source run, requires its immutable report, and atomically inserts
the successor, audit event, and idempotency response. No result/evidence rows are copied.
The ordinary pipeline must produce a new report before latest-decision selection changes;
the predecessor remains byte-for-byte unchanged.

The supplier identity review queue is a read-only tenant projection over immutable
claims and the latest row of each append-only review ledger. It includes only
`UNREVIEWED` and `INCONCLUSIVE` states, joins opportunity and source context, and orders
by immutable claim creation time plus ID for bounded keyset pagination. It does not
create a mutable queue table, duplicate evidence, or modify review state on read.

The research review queue is a second read-only tenant projection over report-bearing
runs whose current state belongs to the domain's reviewable-status set. It joins only
required report/validation columns, then batch-loads issue severities and unknown counts
to reuse the deterministic data-gap policy without N+1 queries or free-text retrieval.
The projection exposes counts and hashes, not report/evidence/free-text bodies, and leaves
approve/reject writes on the existing expected-version transaction.

Research review writes retain rationale in the authorized append-only review ledger but
emit a minimal audit payload containing only decision, before/after status, and resulting
version. This is a forward-only event contract: existing audit rows are never rewritten,
and downstream consumers must not require rationale duplication in new audit events.

The opportunity decision view also builds the executive summary from those same joined
validation, scenario, issue, unknown, and rank-1 rows. This keeps run-level and latest-
opportunity policy identical and prevents a client from combining a summary with a
newer empty run or another tenant's result.

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

Cost coverage is a pure projection over the same component ledger and is shared by the
API and report. A finite reference vocabulary makes coverage auditable while preserving
unknown custom codes. The projection counts evidence classes and zero amounts but does
not calculate a completeness percentage, infer applicability, or create missing costs.

FX inputs are parsed as a shared collection with optional per-scenario overrides.
Persistence creates scenario rows first, then stores each rate with a required scenario
foreign key and its deduplicated evidence reference. The authenticated FX read model
joins scenario, rate, evidence, and source under the tenant-owned run; it deliberately
omits raw evidence bodies while retaining the provenance needed to reproduce the
conversion decision.

The assumption read model queries only the authenticated tenant's run and separates
`ASSUMPTION` from `UNKNOWN` rows. The latest-decision projection reads the same
immutable snapshot so a UI does not need to parse report Markdown. Input parsing
requires bounded non-empty strings; audit events retain counts and run lineage rather
than duplicating commercial note contents.

The data-gap application projection combines persisted validation issues with the
individual unknown-note snapshot. A pure deterministic function orders issues, counts
severity and unknown coverage, and derives the review status for both API and report.
It does not mutate the run or infer completeness from missing records; tenant ownership
is checked before either source collection is read.

The evidence-catalog projection joins tenant-owned evidence to source metadata, then
builds deterministic usage references from price observations and scenario-linked FX
rows. It exposes the stored SHA-256 fingerprint but not `raw_value`. This keeps normal
result consumption provenance-aware while leaving any future raw-evidence access behind
a separate, stronger authorization and retention policy.

Evidence freshness reuses the persisted validation timestamp and the validation
module's shared age/skew constants. The repository counts price and FX references to
each tenant-owned evidence row, normalizes database timestamps to UTC at the adapter
boundary, and invokes a pure projection. Report generation deduplicates the immutable
domain evidence through the same SHA-256 identity function used by persistence, then
calls that projection. Neither surface reads raw evidence into its response.

The price-observation projection joins observation, product match, ranking, evidence,
and source rows only when every record belongs to the same tenant-owned run. It returns
the original commercial fields beside BASE-scenario normalization and match metadata,
avoiding client-side joins that could combine different runs. Raw evidence remains
outside this view.

Quantity analysis is a pure application calculation over evidence-backed observation
points projected by the repository. It uses exact decimal arithmetic and deterministic
product/supplier/group/quantity ordering; both the API and report call the same function.
The canonical product grouping key includes name, variant, and sorted attributes so
different products cannot form a false tier series. The module
does not extrapolate continuous tiers, supplier capacity, negotiation margin, or EOQ.

Observed price distribution is another pure application calculation shared by the API
and report. Repository and report adapters construct the same point shape from the
immutable run, while the calculation groups compatible canonical product, market,
quantity, and unit/currency dimensions and uses exact decimal statistics. The read model
returns source coverage and exclusions without raw evidence; it does not infer benchmark
authority from a user-supplied market-layer label.

Supplier-offer read models join the immutable ranking row to its exact price
observation, evidence row, and source. This prevents clients from treating a detached
score as a decision and keeps normalized and original values visible together. The
summary omits raw evidence content while retaining the URL, retrieval metadata, class,
confidence, and transformation needed for provenance-aware display.

Supplier coverage is calculated by a pure application projection over the same joined
observation/ranking/evidence rows. It aggregates exact identified names while retaining
anonymous observation IDs, returns distinct URL coverage and missing factors, and never
promotes an offer into a verified supplier profile. The API and report share this
calculation; raw evidence remains outside both outputs.

Supplier identity claims enter only with the immutable evidence bundle. Each claim
references one exact retained price observation and one deduplicated evidence record;
claims referring to an observation removed by deterministic deduplication are excluded
with an explicit validation error rather than being reassigned. A shared pure projection
orders claims and initially labels each `UNREVIEWED` for both API and report. It never
mutates the offer's supplier name, ranking, or due-diligence status and does not create
a cross-run supplier profile.

Post-result identity-claim review is a separate append-only ledger. A tenant-scoped
repository query locks the immutable claim row, compares `expected_version` to the
latest ledger version, appends one decision and audit event atomically, and returns a
conflict to stale writers. Reads fold only the latest review into the live claim
projection while retaining every prior decision. The immutable generated report is not
rewritten, so it remains an ingestion-time `UNREVIEWED` snapshot. Review states describe
evidence support, not verified identity.

Incoterm coverage uses a shared versioned code vocabulary also consumed by validation.
The repository projects only tenant-owned observation/evidence rows into a pure
calculator; the report uses the same point contract from its immutable result. Both
surfaces expose recognized/unrecognized/missing declarations, original named-place and
version values, complete-terms counts, and source coverage. Nullable columns preserve
legacy rows without inventing defaults; comparison remains withheld because no route-
specific cost/control/risk scenario model exists.

Offer-terms coverage joins only tenant-owned price observations to their immutable
ranking rows, then invokes a pure application projection also used by reports. The
calculation uses a finite ordered vocabulary for fields the schema can represent and a
separate explicit vocabulary for currently uncaptured commercial terms. This prevents
clients from deriving a misleading percentage or treating rankability as completeness.
Payment terms/method, quote-valid-until time, and lead-time days remain attributes of the
exact evidence-backed offer rather than a mutable supplier profile. Validation compares
quote validity only with the persisted run evaluation time, while ranking exposes absent
terms as unknown factors without changing the versioned score weights.

The executive-summary application policy consumes persisted validation, BASE scenario,
rank-1 evidence-backed offers, and the shared data-gap summary. It emits conservative
machine-readable status/recommendation codes and keeps tied candidates. Repository and
report adapters use the same pure function. Iranian benchmark and gross-spread fields
are structurally present but null until a separately approved comparable-market input
contract exists, preventing presentation code from inventing the missing comparison.

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

The same serialized service records process-local runtime health from actual valid
cache-miss attempts. It distinguishes never observed, last attempt succeeded, and last
attempt failed; a disabled-provider state is composed at the API boundary. Cache hits
have their own counter and cannot overwrite a failed upstream outcome. The health read
is passive, creates no adapter, and makes no network request. Timestamps are
timezone-aware UTC, counters reset on process restart, and exception text is never part
of the health contract.

Provider governance metadata lives in a typed provider registry outside the HTTP
layer. It exposes only controlled operational facts and explicit unknowns. The ECB kill
switch is checked before lazy provider construction, so disabling it cannot trigger a
network request; adding a provider requires a new descriptor rather than ad-hoc API
metadata. The registry also exposes a boolean terms-approval assertion beside the
human-readable review status. Production configuration fails at startup if ECB is
enabled while that assertion is false, keeping an advisory governance state from
silently becoming live egress.

## Configuration

Development, test, and production use environment-specific configuration validated
at startup. Secrets come from environment/secret managers and are redacted from
structured logs. Provider terms approval is a non-secret deployment assertion backed by
an external decision record; it neither stores the legal record nor grants network
access. No environment-specific business rules belong in source code.
