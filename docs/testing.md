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

Authentication integration tests run with authentication enabled and cover missing,
invalid, and valid keys; public health; tenant/actor audit attribution; and identical
`404` responses for cross-tenant aggregate reads and mutations. Configuration tests
verify that production cannot start with authentication disabled and credentials are
configured as SHA-256 digests rather than raw keys. Migration `0007` is exercised in
both upgrade and full rollback paths.

The GitHub Actions quality workflow runs the deterministic suite on Python 3.12 and
starts an ephemeral PostgreSQL 17 service. It upgrades every Alembic migration, checks
model/migration parity, executes the authenticated evidence-to-report transaction
against PostgreSQL (including Decimal, JSON, tenant, audit, and idempotency behavior),
then verifies a complete rollback and re-upgrade. The PostgreSQL test skips locally
unless `TRADE_AGENT_TEST_POSTGRES_URL` is explicitly configured.

SQLite integration connections explicitly enable foreign-key enforcement, so local
tests reject invalid parent/child flush ordering instead of deferring its discovery to
PostgreSQL. Parent scenario rows are flushed before their component ledger entries.
