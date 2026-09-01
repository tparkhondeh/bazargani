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
