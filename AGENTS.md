# AGENTS.md

This repository builds an evidence-first commercial sourcing agent. Read
`docs/specification.md`, `docs/architecture.md`, and `docs/security.md` before
changing behavior.

Non-negotiables:

- Never present mock, inferred, estimated, or unsourced data as fact.
- Preserve source URL, retrieval time, evidence class, original currency/value,
  and transformations.
- Financial calculations use deterministic code and `Decimal`, never an LLM or
  binary floating point.
- Acquisition adapters stay outside domain and calculation modules.
- Reject unsafe URLs and never commit secrets.
- Add or update tests for every calculation or validation change.
- Keep `main` stable; work on focused branches and run the documented quality gates.

Decision records live in `docs/adr/`; update them for significant architectural
changes. MVP scope and sequencing live in `docs/roadmap.md`.

