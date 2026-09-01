# Testing Strategy

- Unit tests for invariants, validation, matching, ranking, and money conversion.
- Golden calculation tests with hand-computed totals and rounding boundaries.
- Provider contract tests shared by every adapter.
- Integration tests for persistence, migrations, API, and partial-provider failure.
- Regression fixtures containing only synthetic/demo or licensed captured content.
- Security tests for SSRF, redirect handling, secret redaction, and hostile content.
- An AI evaluation set of 10–20 Persian/English requests with expected structured
  fields, missing-field questions, and product-match outcomes before enabling LLM
  parsing in production.

The initial deterministic intake regression set lives in
`evals/request_parsing.json` and currently covers Persian/English digits, product
placement, origins, destinations, and missing critical fields. It is a baseline for
future LLM-assisted parsing, not a claim of universal language coverage.

No calculation change passes without exact numeric tests. Network tests are isolated
from the default suite and never rely on mutable market prices.

Scenario-sensitivity tests use hand-computed `Decimal` values for base deltas, signed
percentages, and total range. They also prove that mixed quantity/currency bases emit
no comparison numbers, a zero base emits no percentages, and missing or duplicate
scenario names are rejected. API and report tests lock the same derived result across
both presentation paths.

Calculation-ledger API tests verify semantic scenario/component ordering, exact stored
`Decimal` totals, component-sum reconciliation, formula and evidence-class visibility,
absence of raw evidence, and cross-tenant `404` behavior. The PostgreSQL integration
path repeats component reconciliation against migrated production types.

Scenario-FX tests assign synthetic rates of 90/100/110 to optimistic/base/conservative
inputs, lock their exact per-unit outputs and sensitivity, then read the rates back with
the correct scenario/source lineage. Regression tests retain the legacy shared-rate
input shape, reject ambiguous duplicate identities within one scenario, omit raw
evidence from API views, and enforce cross-tenant `404`. PostgreSQL CI upgrades and
rolls back the scenario foreign-key migration and exercises the resulting read path.

Assumption-ledger tests cover structured run reads, inclusion in the evidence-backed
latest decision, deterministic separation from unknowns, cross-tenant `404`, and
PostgreSQL persistence. Parser tests reject nested objects, blank notes, and individual
values beyond 5,000 characters before report generation or storage.

The deterministic validation suite fixes its evaluation timestamp and covers clean
fact-backed input, exact deduplication, stale evidence, price outliers, zero price,
product conflicts, and quantity/MOQ incompatibility. API integration tests verify
that the validation ledger and non-complete run status are persisted atomically with
the decision report.

Product-match tests cover Persian/Arabic normalization, exact product/variant,
comparable and substitute classes, conflicting attributes, missing features, and the
guard that prevents generic attributes from promoting unrelated products. API tests
verify the match ledger is persisted and retrievable with its raw features and policy
version.

Supplier-offer ranking tests cover cross-currency normalization, price-versus-
evidence tradeoffs, neutral single-offer pricing, MOQ ineligibility, missing FX,
anonymous suppliers, and deterministic tied ranks. Integration tests verify the
ranking ledger and unknown diligence factors are returned by the API and committed in
the same result transaction.

Idempotency integration tests cover required-header validation, first-write response,
same-key/same-payload replay without duplicate rows, stable report/version hashes, and
same-key/different-payload conflict. The database unique constraint is retained as the
final concurrent-write guard.

Request-limit tests cover declared oversized JSON, chunked bodies without a content
length, unchanged replay under the limit, stable `413`/correlation contracts, excessive
observation counts, and invalid nested container types.

Validation-response tests inject a synthetic commercial secret into invalid input and
into exception message/context/URL fields, then prove none is reflected. They verify
the allowlisted location/type/generic-message contract and enforce the 50-detail bound
plus explicit omission marker.

Domain-error regression tests place a synthetic secret in a negative cost identifier,
exercise the full opportunity/run/bundle endpoint, and verify that the raw invariant
message is replaced by the generic `INVALID_INPUT` reason. Separate tests retain safe
specific messages for explicitly public missing-unit and destination-mismatch errors.

Response-header tests cover public success, authenticated success, authentication
failure, and pre-parser body-limit rejection. They verify no-store/no-cache,
anti-sniff/frame/referrer/device-policy controls, API-key `Vary`, public-route
exclusion, and case-insensitive preservation of an existing `Vary` value.

Unexpected-error tests inject a provider exception containing a synthetic commercial
secret. With production-style exception propagation disabled, they verify the stable
correlated `500`, no-store/anti-sniff headers, and absence of the secret and exception
class from the response. Known provider failures remain on their explicit `502` path.

Authentication integration tests run with authentication enabled and cover missing,
invalid, and valid keys; public health; tenant/actor audit attribution; and identical
`404` responses for cross-tenant aggregate reads and mutations. Configuration tests
verify that production cannot start with authentication disabled and credentials are
configured as SHA-256 digests rather than raw keys. Migration `0007` is exercised in
both upgrade and full rollback paths.

Rate-limit tests use a deterministic monotonic clock to cover allowance, retry timing,
window reset, and tenant isolation. API tests prove that rotated keys for one tenant
share a budget, health remains public, invalid credentials remain `401`, and rejected
traffic receives a correlation-preserving `429` plus `Retry-After` without tenant data.

The GitHub Actions quality workflow runs the deterministic suite on Python 3.12 and
starts an ephemeral PostgreSQL 17 service. It upgrades every Alembic migration, checks
model/migration parity, executes the authenticated evidence-to-report transaction
against PostgreSQL (including Decimal, JSON, tenant, audit, and idempotency behavior),
then verifies a complete rollback and re-upgrade. The PostgreSQL test skips locally
unless `TRADE_AGENT_TEST_POSTGRES_URL` is explicitly configured.

The same workflow installs only the exact `requirements.lock` environment, verifies
package compatibility with `pip check`, and runs a strict `pip-audit` advisory scan
against that lock. The audit needs network access to current vulnerability data and a
reported known vulnerability blocks the quality job; exceptions must be explicitly
reviewed and documented rather than silently ignored.

Readiness tests keep the embedded required revision equal to Alembic's single head,
distinguish unmanaged auto-create mode, accept only the exact managed revision, and
collapse missing/stale schema into a stable public `503` without database details.
PostgreSQL integration verifies `/ready` after the real migration upgrade.

SQLite integration connections explicitly enable foreign-key enforcement, so local
tests reject invalid parent/child flush ordering instead of deferring its discovery to
PostgreSQL. Parent scenario rows are flushed before their component ledger entries.

Review workflow tests prove that manual transitions cannot fabricate system outcomes,
wrong versions conflict, other tenants receive `404`, and approve/reject map only from
reviewable states to terminal outcomes. API and PostgreSQL integration tests verify
that the review row, actor/rationale, run status/version, and audit event persist
atomically.

Opportunity workflow tests cover permitted progress/resume paths, forbidden skips,
self-transition, and terminal reopening. API integration proves version conflicts,
tenant-hiding `404`, correlated actor attribution, and the exact before/after/version
audit payload; PostgreSQL integration exercises the real locked transition path.

Opportunity-context API tests cover partial updates, whitespace normalization,
explicit null clearing, timezone normalization, naive-datetime rejection, stale
versions, cross-tenant hiding, and absence of commercial note content from audit
payloads. PostgreSQL integration verifies the migrated columns and timestamp response.

Latest-decision tests prove that a newer empty run cannot hide the last evidence-backed
result, scenario ordering is deterministic, all equal rank-1 offers survive the
projection, cross-tenant access returns `404`, and tenant metadata is absent.
PostgreSQL integration verifies the report hash and run identity across the joined view.

Supplier-offer read-model tests verify that ranking rows join to the correct original
amount/currency, quantity, MOQ, Incoterm, source, evidence class, and confidence. Tie
tests retain distinct source URLs, while response assertions ensure raw evidence values
are not copied into the ranking or latest-decision payloads.

Markdown-injection regression tests place HTML tags, forged headings, nested-link
syntax, newlines, and embedded backticks into product, supplier, source, destination,
cost, assumption, and unknown fields. They verify structure is escaped, links stay
bound to the percent-encoded source URL, and adaptive code spans remain balanced.

Pagination tests cover UTC/UUID cursor round trips, malformed and oversized cursors,
maximum page size, stable multi-page traversal without duplicates, and tenant
isolation. PostgreSQL integration repeats multi-page timestamp traversal so SQLite
date encoding cannot conceal a production ordering bug.

Opportunity-history filter tests combine exact lifecycle status, multi-page cursors,
invalid enum input, and a second tenant to prove filtering cannot expose unrelated
aggregates or silently broaden a query.

Audit-history integration tests create events for two tenants, traverse multiple
pages without duplicates, verify actor/action/aggregate fields, reject malformed or
excessive pagination, and prove that one tenant never receives the other's event or a
redundant tenant identifier. PostgreSQL integration compares the fully paged result
with the tenant's stored audit-event count.

ECB provider tests use captured synthetic contract rows and cover latest-observation
selection, provenance, invalid currency, and malformed upstream data. Cache tests
verify lazy construction, case-insensitive hits, expiry/refetch, and no stale fallback.
API tests verify the evidence-rich response plus stable `422` and `502` contracts; a
separate read-only smoke check confirmed the documented official endpoint on
2026-09-01 without turning the live value into a test fixture.

Provider-registry tests require authentication, verify the controlled ECB descriptor
and explicit pending/unknown governance fields, toggle the kill switch, and prove a
disabled request returns before the injected provider receives any call.
