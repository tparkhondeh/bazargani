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
  explainable confidence, product matching, and partial-result orchestration.
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

Result submission uses a scope-and-key idempotency ledger with a SHA-256 canonical
request hash. The immutable response snapshot and idempotency record commit in one
transaction. Same-key/same-hash retries replay the snapshot; same-key/different-hash
requests fail explicitly, including after a concurrent unique-key race.

The HTTP boundary buffers only bounded mutation bodies. It rejects a declared or
streamed body above the configured maximum before validation/use-case execution and
replays accepted chunks unchanged to FastAPI. Independent structural limits prevent a
small but combinatorially excessive evidence bundle from exhausting calculation or
database resources.

The API authenticates a secret key at the boundary, resolves it to an immutable
tenant/actor principal, and passes that principal explicitly through application
ports. Aggregate reads and writes include tenant predicates; an identifier owned by
another tenant is deliberately indistinguishable from a missing identifier (`404`).
Health/readiness remain public and expose no tenant data.

System-derived research outcomes and operator actions use separate paths. The generic
transition route permits only operational lifecycle changes; a review-required result
can reach `COMPLETED` or `CANCELLED` only through an append-only review decision. The
review row, locked run version update, and audit event share one transaction.

## Configuration

Development, test, and production use environment-specific configuration validated
at startup. Secrets come from environment/secret managers and are redacted from
structured logs. No environment-specific business rules belong in source code.
