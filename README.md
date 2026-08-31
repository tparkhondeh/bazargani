# Bazargani Trade Intelligence Agent

An evidence-first vertical slice for turning a product sourcing request into a
reproducible landed-cost decision report.

## Current slice

The first slice accepts a JSON research case containing the user's request,
source-backed price observations, point-in-time FX rates, and explicit cost
assumptions. It validates provenance, calculates optimistic/base/conservative
landed-cost scenarios with `Decimal`, and emits a Persian Markdown report.

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

The evidence-bundle endpoint requires a version-matched `RUNNING` research run. It
calculates and persists evidence, price observations, point-in-time FX, all three
landed-cost scenarios, assumptions/unknowns, an immutable report snapshot, and an
audit event in one transaction.
