# Architecture

## Decision

Use a Python modular monolith. Domain rules and calculation modules have no web,
database, scraper, or model dependencies. Application services orchestrate ports;
adapters implement acquisition, persistence, LLM, and delivery concerns.

```text
CLI / future FastAPI / future RTL UI
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
- future `infrastructure`: PostgreSQL, queues, telemetry, HTTP clients.

## Options rejected for now

- Microservices: operational and consistency cost without independent scaling need.
- Agent framework as the core: hides deterministic state transitions and adds churn.
- Browser-first scraping: fragile, legally variable, difficult to secure and test.
- LLM-owned workflow/calculation: irreproducible and unsafe for financial decisions.

## Reliability

Research steps have explicit statuses and eventually persist checkpoints. Each
provider has timeout, bounded retry, rate-limit handling, caching, and an isolated
failure result. A run may complete partially with visible data gaps.

## Configuration

Development, test, and production use environment-specific configuration validated
at startup. Secrets come from environment/secret managers and are redacted from
structured logs. No environment-specific business rules belong in source code.
