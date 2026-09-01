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

Status: core foundation implemented. Remaining hardening includes idempotency
retention/cleanup policy, OIDC/role authorization,
credential rotation automation, distributed rate limiting, and production backup
rehearsal. Hashed API-key authentication, fail-closed production configuration,
tenant-scoped repositories, and actor-aware audit events are implemented as the
service-to-service baseline. Atomic bundle-submission idempotency is implemented.
The append-only approve/reject review ledger, rationale requirement, optimistic
locking, and protected system-derived statuses are implemented; named-user identity,
role policy, reassignment, and review queues remain future work.
The opportunity lifecycle now has explicit version-checked, tenant-scoped transitions
with atomic audit history and terminal won/lost states. The initial transition graph
still requires commercial stakeholder validation before production activation.
Versioned opportunity workflow context (`next_action`, timezone-aware `deadline`, and
`notes`) is implemented with partial clearing and value-redacted audit metadata;
assignment, reminders, and historical note revisions remain deferred.
An evidence-backed latest-decision projection now joins each opportunity to its newest
report-bearing run, validation, scenario summaries, and all leading tied offers for
future result/history UI use.
PostgreSQL 17 migration parity, authenticated vertical-slice integration, and full
migration rollback/re-upgrade are enforced in CI. Public readiness now checks both
database connectivity and the exact release migration head, while liveness remains
independent.
Exact Python dependency locking, compatibility verification, third-party inventory,
and a blocking known-vulnerability audit are enforced in CI; ongoing upgrade review
and release-time re-audit remain operational responsibilities.
Bounded tenant-scoped keyset pagination for opportunity and research-run history is
implemented as the data-access foundation for the RTL UI. The append-only audit trail
is also exposed through bounded, tenant-scoped keyset pagination with actor and
correlation metadata. Opportunity history also supports indexed exact-status filtering.
Bounded HTTP bodies and evidence-bundle collection limits are implemented; distributed
rate limiting remains part of authentication/production hardening. A tenant-aware,
per-process fixed-window baseline is implemented with shared budgets across rotated
keys, stable `429` responses, and explicit multi-worker limitations. Request-schema
errors use a bounded non-reflective public contract that excludes rejected values and
validation context. Domain/parser exception messages are private by default and only
explicit safe input errors cross the HTTP boundary. No-store and browser response
hardening apply consistently to success and error paths; unexpected failures use a
generic correlated `500` without exception text, while TLS/HSTS remains an edge gate.
Deterministic data-quality validation, exact
observation deduplication, persisted validation issues, and explainable confidence are
implemented. The deterministic product-match baseline and persistence are implemented;
assisted/semantic matching evaluation remains in Phase 3.
The deterministic quantity-aware supplier-offer ranking baseline is implemented;
ranking/latest-decision reads now carry original offer context and source provenance.
Verified supplier profiles, capacity/certification evidence, and multi-tier quote
history remain Phase 3/5 work.

## Phase 3 — First approved real providers

Integrate one manufacturing/wholesale source and one Iranian benchmark source via
contract-tested adapters. Add safe URL fetcher, rate limits, cache, partial results,
assisted product matching, deduplication, and provider health.

Status: the official ECB adapter is exposed through the authenticated API with
provenance, bounded safe HTTP, TTL caching, and stable failure behavior. It remains an
informational EUR reference only. Approved manufacturing/wholesale and Iranian
benchmark sources, shared provider telemetry, and distributed rate control remain.

## Phase 4 — Assisted intelligence and RTL UI

LLM-assisted request parsing/matching with evals and cost telemetry; Persian RTL UI
for new research, progress, result, assumptions, and opportunity history.

## Phase 5 — MVP hardening

OIDC/role authorization, review queues/escalation, verified supplier profiles, incoterm
and quantity analysis, security/load/failure testing, operational runbooks,
dependency notices, production migration and rollback rehearsal.

### Quality gate per phase

Tests, lint, type check, calculation regression, migration check when applicable,
dependency/security/license scan, documentation review, and evidence/provenance
audit. `main` receives only reviewed, reversible changes.
