# Bazargani Trade Intelligence Agent

An evidence-first vertical slice for turning a product sourcing request into a
reproducible landed-cost decision report.

## Current slice

The first slice accepts a JSON research case containing the user's request,
source-backed price observations, point-in-time FX rates, and explicit cost
assumptions. It validates provenance, calculates optimistic/base/conservative
landed-cost scenarios with `Decimal`, and emits a Persian Markdown report.

It intentionally does **not** invent prices or scrape arbitrary URLs. Automated
source adapters, persistence, API, and RTL web UI are phased work documented in
`docs/roadmap.md`.

## Run locally

Python 3.12+ is required.

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
