# Master Implementation Plan and Roadmap

## Phase 0 — Discovery and foundation (current)

Specification, modular boundaries, domain vocabulary, threat model, source policy,
open-source evaluation, ADRs, repository conventions, and quality gates.

## Phase 1 — Deterministic vertical slice (current)

Validated evidence bundle → product/price observations → point-in-time FX → three
landed-cost scenarios → Persian decision report. CLI, golden tests, explicit demo
fixture, no invented market facts.

## Phase 2 — Persistence and service boundary

PostgreSQL/Alembic repositories, append-only audit trail, FastAPI endpoints,
idempotency, research-run state machine, structured logs/correlation IDs, Docker
development environment, backup/restore procedure.

Status: core foundation implemented. Remaining hardening includes PostgreSQL
integration in CI, authentication/tenant scope, idempotency retention/cleanup policy,
and production backup rehearsal. Atomic bundle-submission idempotency is implemented.
Deterministic data-quality validation, exact
observation deduplication, persisted validation issues, and explainable confidence are
implemented. The deterministic product-match baseline and persistence are implemented;
assisted/semantic matching evaluation remains in Phase 3.
The deterministic quantity-aware supplier-offer ranking baseline is implemented;
verified supplier profiles, capacity/certification evidence, and multi-tier quote
history remain Phase 3/5 work.

## Phase 3 — First approved real providers

Integrate one manufacturing/wholesale source and one Iranian benchmark source via
contract-tested adapters. Add safe URL fetcher, rate limits, cache, partial results,
assisted product matching, deduplication, and provider health.

## Phase 4 — Assisted intelligence and RTL UI

LLM-assisted request parsing/matching with evals and cost telemetry; Persian RTL UI
for new research, progress, result, assumptions, and opportunity history.

## Phase 5 — MVP hardening

Authentication/authorization, human review workflow, supplier ranking, incoterm and
quantity analysis, security/load/failure testing, operational runbooks, dependency
notices, production migration and rollback rehearsal.

### Quality gate per phase

Tests, lint, type check, calculation regression, migration check when applicable,
dependency/security/license scan, documentation review, and evidence/provenance
audit. `main` receives only reviewed, reversible changes.
