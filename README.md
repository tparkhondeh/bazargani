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
```

See `docs/` for specification, architecture, security, data model, source
strategy, open-source evaluation, testing strategy, and roadmap.

## API foundation

Phase 2 adds PostgreSQL/Alembic persistence and a loopback FastAPI service. See
`docs/operations.md` for local commands. Initial endpoints are:

- `GET /health` and `GET /ready`
- `POST /api/v1/requests/parse`
- `POST /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `POST /api/v1/opportunities/{id}/research-runs`
- `POST /api/v1/research-runs/{id}/transitions`
- `POST /api/v1/research-runs/{id}/evidence-bundle`
- `GET /api/v1/research-runs/{id}/report`
- `GET /api/v1/research-runs/{id}/validation`
- `GET /api/v1/research-runs/{id}/product-matches`
- `GET /api/v1/research-runs/{id}/supplier-offer-rankings`

The evidence-bundle endpoint requires a version-matched `RUNNING` research run. It
calculates and persists evidence, price observations, point-in-time FX, all three
landed-cost scenarios, validation summary/issues, assumptions/unknowns, an immutable
report snapshot, and an audit event in one transaction. A result with warnings is
marked `NEEDS_VERIFICATION`; material conflicts are marked `NEEDS_HUMAN_REVIEW`
instead of being silently reported as complete.

Every evidence-bundle submission also requires an `Idempotency-Key` header containing
1–128 URL-safe identifier characters. An exact retry returns the original immutable
completion with `idempotency_replayed=true`; reusing the key for a different run body
returns `409 IDEMPOTENCY_CONFLICT`. The idempotency record is committed in the same
transaction as the research result.

Mutating HTTP requests are capped at 2,000,000 bytes by default, including chunked
requests without `Content-Length`; oversized requests receive `413 REQUEST_TOO_LARGE`.
The evidence parser also caps observations (500), FX rates (100), scenarios (3),
costs per scenario (100), notes per kind (200), and product attributes (100).
