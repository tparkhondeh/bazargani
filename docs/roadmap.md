# Master Implementation Plan and Roadmap

## Phase 0 — Discovery and foundation (current)

Specification, modular boundaries, domain vocabulary, threat model, source policy,
open-source evaluation, ADRs, repository conventions, and quality gates.

## Phase 1 — Deterministic vertical slice (current)

Validated evidence bundle → product/price observations → point-in-time FX → three
landed-cost scenarios → Persian decision report. CLI, golden tests, explicit demo
fixture, no invented market facts.

Status: deterministic scenario sensitivity is implemented for equal quantity/currency
bases, including exact deltas in the API and Persian report. Mixed bases and a zero
denominator remain explicit non-comparable states; EOQ and quantity-tier optimization
remain deferred until supported commercial inputs exist.
Scenario-specific point-in-time FX overrides and persisted scenario lineage are also
implemented. A provenance-rich run endpoint exposes the exact rates used without raw
evidence bodies; automated Iran-market FX sources remain blocked on source approval.
Structured assumption/unknown snapshots are implemented at run and latest-decision
level. Explicit correction now creates an idempotent, predecessor-linked empty successor
run, preserves old report hashes, and requires the corrected full bundle to pass the
ordinary calculation pipeline. Selective dependency-graph recalculation remains future
work; immutable completed runs are not edited in place.
A structured data-gap projection now combines validation errors/warnings and individual
declared unknowns for API and report consumers, while explicitly refusing to equate an
empty ledger with commercial completeness. Provider-attributed runtime gaps remain part
of the future resumable acquisition pipeline.
A tenant-scoped evidence catalog now connects deduplicated source metadata and content
fingerprints to price/FX usages without returning raw bodies. Role-gated raw-evidence
review, retention rules, and legal export policy remain future governance work.
An evidence-backed price-observation projection now provides original offer context,
BASE-normalized comparison values, product match, and source metadata for future price
distribution and Iranian benchmark UI. Actual approved benchmark acquisition remains.
Observed-quote quantity analysis is implemented with deterministic per-supplier series
and adjacent normalized price deltas in the API and Persian report. True EOQ/economic
order range remains deferred until the required operational/economic inputs exist.
Exact observed-price distributions are implemented for compatible product, quantity,
unit/currency, and market-layer groups, including min/median/max/range and source
coverage in the API and Persian report. Approved Iranian benchmark acquisition and
representativeness rules remain Phase 3 work; labels alone never establish a benchmark.
A conservative executive summary now exposes BASE landed cost, all leading unverified
offer candidates, validation/gap context, and deterministic review action. Iranian
market price and gross spread remain withheld/null until an approved comparable
benchmark adapter and contract are implemented.

## Phase 2 — Persistence and service boundary

PostgreSQL/Alembic repositories, append-only audit trail, FastAPI endpoints,
idempotency, research-run state machine, structured logs/correlation IDs, Docker
development environment, backup/restore procedure.

Status: core foundation implemented. Remaining hardening includes idempotency
retention/cleanup policy, OIDC/named-user authorization,
credential rotation automation, distributed rate limiting, and production backup
rehearsal. Hashed API-key authentication, fail-closed production configuration,
tenant-scoped repositories, and actor-aware audit events are implemented as the
service-to-service baseline. Atomic bundle-submission idempotency is implemented.
The append-only approve/reject review ledger, rationale requirement, optimistic
locking, and protected system-derived statuses are implemented. A bounded tenant-scoped
run-review queue now exposes report hash, validation lineage, gap counts, and the exact
version required for review. New research-review audit events omit rationale while the
authorized review ledger retains it. Digest-bound `RESEARCH_REVIEWER` and
`SUPPLIER_IDENTITY_REVIEWER` roles now fail closed across their queue, history, and
write endpoints. The generic audit API also applies review-action allowlists so legacy
payloads cannot disclose historical rationale or unexpected private fields. Named-user
identity and role policy, assignment/escalation, and reassignment remain future work.
The opportunity lifecycle now has explicit version-checked, tenant-scoped transitions
with atomic audit history and terminal won/lost states. The initial transition graph
still requires commercial stakeholder validation before production activation.
Versioned opportunity workflow context (`next_action`, timezone-aware `deadline`, and
`notes`) is implemented with partial clearing and value-redacted audit metadata;
assignment, reminders, and historical note revisions remain deferred.
An evidence-backed latest-decision projection now joins each opportunity to its newest
report-bearing run, validation, scenario summaries, and all leading tied offers for
future result/history UI use. It also embeds the conservative executive summary so the
UI does not reimplement recommendation, gap, candidate, or benchmark-withholding policy.
A tenant-scoped structured landed-cost ledger now exposes scenario totals, every
calculation component/formula/evidence class, and shared sensitivity without Markdown
parsing. A scenario cost-coverage projection now highlights recorded, unrecorded
reference, custom, zero, and evidence-class coverage without inventing applicability or
amounts; richer evidence drill-down and UI visualization remain later work.
An evidence-freshness projection now applies the persisted validation time and shared
30-day/five-minute policy boundaries to deduplicated evidence and exact price/FX usage
counts. Provider-specific validity windows and live refresh workflows remain future
work; recency is not treated as proof of source quality.
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
New decision reports also escape untrusted HTML/Markdown structure and encode link
targets; strict client-side Markdown sanitization remains an RTL UI requirement.
Deterministic data-quality validation, exact
observation deduplication, persisted validation issues, and explainable confidence are
implemented. The deterministic product-match baseline and persistence are implemented;
assisted/semantic matching evaluation remains in Phase 3.
The deterministic quantity-aware supplier-offer ranking baseline is implemented;
ranking/latest-decision reads now carry original offer context and source provenance.
A run-level supplier evidence-coverage view now aggregates offer/source and commercial-
field coverage while keeping every due-diligence status unverified and anonymous offers
separate. Verified supplier profiles, source independence, capacity/certification
evidence, and multi-tier quote history remain Phase 3/5 work.
A run-level Incoterm evidence-coverage view now groups exact declarations against the
Incoterms 2020 reference vocabulary, preserves unknown/missing codes, and explicitly
withholds comparison. Structured named-place and declared-version capture is now
persisted and included in completeness validation; comparable route-specific cost,
control, and risk scenarios remain Phase 5 work.
A per-offer terms-coverage projection now distinguishes ten structured fields, including
payment terms/method, quote validity, and lead-time days, from capacity, certification,
warranty, and inspection terms that remain outside the schema. It returns exact field
names and counts without a misleading percentage. Quote expiry is evaluated against the
immutable run time, while negotiation/acceptability and remaining term models stay in
Phase 5.

Immutable offer-scoped supplier identity claims now retain a claimed legal name,
jurisdiction, registration number, and dedicated evidence inside the result snapshot.
They begin explicitly unreviewed, do not affect ranking/due diligence, and do not form
a supplier profile. A tenant-scoped append-only review ledger now records versioned
evidence-supported, evidence-contradicted, or inconclusive decisions without rewriting
the report or claiming verified identity. A bounded tenant review-queue projection now
surfaces only unreviewed and inconclusive claims with opportunity/source context. Named
reviewer identity/roles, assignment/escalation, cross-run entity resolution, verified
profiles, capacity, and certification evidence remain Phase 3/5 work.

## Phase 3 — First approved real providers

Integrate one manufacturing/wholesale source and one Iranian benchmark source via
contract-tested adapters. Add safe URL fetcher, rate limits, cache, partial results,
assisted product matching, deduplication, and provider health.

Status: the official ECB adapter is exposed through the authenticated API with
provenance, bounded safe HTTP, TTL caching, and stable failure behavior. It remains an
informational EUR reference only. Approved manufacturing/wholesale and Iranian
benchmark sources, shared provider telemetry, and distributed rate control remain.
The provider now has a typed authenticated governance descriptor and configuration kill
switch. Production now fails closed when ECB is enabled without an explicit
terms-approval assertion; formal authorization evidence and network review are still
prerequisites. A 2026-09-01 review deferred eBay Browse and Best Buy Products adapters
until their production/commercial access and content-use constraints are approved; UN
Comtrade remains contextual trade data rather than quote evidence. Passive authenticated
ECB health now reports process-local outcomes and counters from real request-driven
attempts without probes or exception detail. Cross-worker telemetry, alert aggregation,
and approved manufacturing/wholesale and Iranian benchmark providers remain.

## Phase 4 — Assisted intelligence and RTL UI

LLM-assisted request parsing/matching with evals and cost telemetry; Persian RTL UI
for new research, progress, result, assumptions, and opportunity history.

Status: the deterministic intake baseline now handles Persian/English digits, product
placement, known location aliases, and bounded open-vocabulary locations following
explicit markers. Conflicting origin/destination mentions are disclosed and block
automatic start rather than being resolved by first-match order. The first bounded
constraint extractor recognizes a requested Incoterm code only inside an explicit
clause, rejects unsupported or conflicting declarations into clarification, and does
not infer a version/named place or affect calculations. Additional constraint extraction,
LLM assistance, eval/cost telemetry, and the RTL UI remain future work.

## Phase 5 — MVP hardening

OIDC/role authorization, queue assignment/escalation, verified supplier profiles,
route-specific Incoterm scenario comparison and full EOQ analysis,
security/load/failure testing, operational runbooks, dependency notices, production
migration and rollback rehearsal.

### Quality gate per phase

Tests, lint, type check, calculation regression, migration check when applicable,
dependency/security/license scan, documentation review, and evidence/provenance
audit. `main` receives only reviewed, reversible changes.
