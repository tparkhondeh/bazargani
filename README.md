# Bazargani Trade Intelligence Agent

An evidence-first vertical slice for turning a product sourcing request into a
reproducible landed-cost decision report.

## Current slice

The first slice accepts a JSON research case containing the user's request,
source-backed price observations with explicit units, scenario-linked point-in-time
FX rates, and explicit cost assumptions. It validates provenance and freshness,
removes exact duplicates, flags conflicts and price outliers, calculates optimistic/base/
conservative landed-cost scenarios with `Decimal`, and emits a Persian Markdown
report with an explainable confidence score. Each retained price is also classified
as an exact product, exact variant, comparable, similar, or substitute using a
policy-versioned deterministic feature ledger.
It also ranks actionable supplier offers within comparable unit/currency groups using
quantity fit, MOQ, product match, evidence quality, commercial completeness, and
normalized price—while keeping supplier due diligence explicitly unresolved.
The decision view and new reports also expose exact per-unit deltas and percentage
sensitivity around the base scenario. Comparison is withheld when scenario quantities
or currencies differ, and the output explicitly does not claim to be an EOQ model.
Observed BASE-normalized prices also expose deterministic min/median/max/range
distributions, but only inside identical product, quantity, unit/currency, and market-
layer groups; these submitted observations are not asserted to be market benchmarks.
Persisted validation issues and declared unknowns are also projected as a structured
data-gap summary for human verification workflows.
Supplier coverage aggregates only retained offer/source fields and keeps due diligence
explicitly unverified; distinct URLs are not presented as independent sources.
An executive summary turns the validated run into conservative decision codes, leading
unverified candidates, BASE landed cost, and explicit withheld market/spread fields.
Trade-cost coverage compares recorded scenario component codes with a transparent
reference vocabulary without inferring applicability or missing amounts.
Incoterm coverage groups only declared offer codes against the Incoterms 2020
reference vocabulary and withholds route-specific comparison when scenarios are absent.
Price observations now retain an optional Incoterm named place and declared version;
partial declarations become explicit validation and ranking gaps.
Offer-terms coverage exposes exact per-offer presence for ten structured commercial
fields while separately naming important terms outside the current schema.
Evidence freshness applies the validation run's immutable evaluation timestamp and
policy thresholds to every deduplicated evidence item and its exact usage count.

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
python -m compileall -q src tests
python -m pip check
python -m pip_audit -r requirements.lock --strict --progress-spinner off
```

The advisory audit requires network access and fails the local/CI gate when a known
vulnerability is reported for the exact locked environment.

See `docs/` for specification, architecture, security, data model, source
strategy, open-source evaluation, testing strategy, and roadmap.

## API foundation

Phase 2 adds PostgreSQL/Alembic persistence and a FastAPI service. See
`docs/operations.md` for local commands. Initial endpoints are:

- `GET /health` and `GET /ready`
- `POST /api/v1/requests/parse`
- `GET /api/v1/providers`
- `GET /api/v1/providers/ecb-fx-reference/health`
- `GET /api/v1/reference-rates/ecb/{quote_currency}`
- `GET /api/v1/audit-events`
- `GET /api/v1/research-review-queue`
- `GET /api/v1/supplier-identity-review-queue`
- `POST /api/v1/opportunities`
- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `POST /api/v1/opportunities/{id}/transitions`
- `PATCH /api/v1/opportunities/{id}/context`
- `GET /api/v1/opportunities/{id}/latest-decision`
- `POST /api/v1/opportunities/{id}/research-runs`
- `GET /api/v1/opportunities/{id}/research-runs`
- `POST /api/v1/research-runs/{id}/successors`
- `POST /api/v1/research-runs/{id}/transitions`
- `POST /api/v1/research-runs/{id}/reviews`
- `GET /api/v1/research-runs/{id}/reviews`
- `POST /api/v1/research-runs/{id}/evidence-bundle`
- `GET /api/v1/research-runs/{id}/report`
- `GET /api/v1/research-runs/{id}/validation`
- `GET /api/v1/research-runs/{id}/data-gaps`
- `GET /api/v1/research-runs/{id}/landed-cost-scenarios`
- `GET /api/v1/research-runs/{id}/cost-coverage`
- `GET /api/v1/research-runs/{id}/fx-rates`
- `GET /api/v1/research-runs/{id}/assumptions`
- `GET /api/v1/research-runs/{id}/evidence`
- `GET /api/v1/research-runs/{id}/evidence-freshness`
- `GET /api/v1/research-runs/{id}/price-observations`
- `GET /api/v1/research-runs/{id}/incoterm-coverage`
- `GET /api/v1/research-runs/{id}/offer-terms-coverage`
- `GET /api/v1/research-runs/{id}/quantity-analysis`
- `GET /api/v1/research-runs/{id}/price-distribution`
- `GET /api/v1/research-runs/{id}/product-matches`
- `GET /api/v1/research-runs/{id}/supplier-offer-rankings`
- `GET /api/v1/research-runs/{id}/supplier-coverage`
- `GET /api/v1/research-runs/{id}/supplier-identity-claims`
- `POST /api/v1/research-runs/{id}/supplier-identity-claims/{claim_id}/reviews`
- `GET /api/v1/research-runs/{id}/supplier-identity-claims/{claim_id}/reviews`
- `GET /api/v1/research-runs/{id}/executive-summary`

`/health` and `/ready` are public for orchestration. Health reports process liveness;
readiness checks database connectivity and, when Alembic manages the schema, requires
the exact migration head shipped with the release. Missing/stale schema returns a
stable `503 NOT_READY`. Every `/api/v1` endpoint is authenticated when
`TRADE_AGENT_AUTH_ENABLED=true` and requires `X-API-Key`. Only SHA-256 key digests are
configured; the resolved tenant and a non-secret key fingerprint are propagated into
tenant-scoped repository queries and audit events. Production configuration fails at
startup if authentication is disabled. Review queues, review history, and review writes
also require an explicit credential role: `RESEARCH_REVIEWER` or
`SUPPLIER_IDENTITY_REVIEWER`. A valid key without the required role receives the stable
`403 AUTHORIZATION_DENIED` contract; cross-tenant identifiers remain hidden as `404`
after role authorization succeeds.

Authenticated API traffic has a per-tenant, per-process fixed-window limit (default
120 requests per 60 seconds). Every key mapped to a tenant shares its budget;
exhaustion returns `429 RATE_LIMIT_EXCEEDED` with `Retry-After`. Health/readiness are
excluded. A trusted edge/distributed limiter is still required for production because
budgets multiply across workers and reset with the process.

Opportunity lifecycle changes use an explicit state machine and require the current
aggregate version. The locked status/version update and actor-attributed audit event
commit atomically. `WON` and `LOST` are terminal; `ON_HOLD` can resume only through a
named target stage. The initial transition policy is documented in ADR 0007 and must
be validated with commercial stakeholders before production use.

The opportunity context endpoint partially updates `next_action`, timezone-aware
`deadline`, and `notes` under the same row-lock and expected-version boundary. Values
can be explicitly cleared with JSON `null`. The audit event records only field names
and the resulting version so commercial note content is not duplicated into the audit
ledger.

The latest-decision projection returns the newest research run under an opportunity
that actually has an immutable report, together with validation, the three landed-cost
summaries, and every rank-1 offer (including ties). A newer empty/in-progress run does
not erase the last evidence-backed decision, and the endpoint never chooses one tied
supplier arbitrarily. It derives scenario sensitivity at read time using `Decimal`;
mixed quantity/currency bases return `MIXED_BASIS` without comparison numbers.

Supplier ranking responses are evidence-backed offer views: they include the original
price/currency, quoted quantity, unit, MOQ, Incoterm, payment/timing terms, source
identity/URL, retrieval time, evidence class/confidence, and transformation beside the
deterministic score.
Raw evidence bodies are not duplicated into these decision summaries.
The same projection now embeds the conservative executive summary, so opportunity UIs
receive review/recommendation codes, candidate state, BASE landed cost, data-gap context,
and withheld Iranian benchmark/spread fields without rebuilding run policy client-side.

Statuses derived from validation cannot be manually promoted to `COMPLETED` through
the generic transition endpoint. An authenticated actor must record an `APPROVE` or
`REJECT` review with a rationale and expected version. The decision, status/version
change, actor fingerprint, and audit event commit atomically; cross-tenant review
access returns `404`. API-key attribution is a service baseline, not proof of a named
human identity. Credential-level reviewer roles enforce least privilege now, while
OIDC/SSO and named-user roles remain required for production user accountability. The
full rationale stays in the role-authorized review ledger; new audit events record only
the decision, transition, and resulting version to avoid duplicating commercial free
text.

Opportunity, research-run, and audit-event history endpoints use newest-first opaque
cursor pagination. `limit` is bounded to 1–100 (default 50); `next_cursor` is returned
only when another page exists. Cursors encode ordering state, not authorization: every
query independently applies the authenticated tenant predicate and malformed or
oversized cursors fail with `422`. Audit responses expose the non-secret actor
fingerprint, correlation/aggregate metadata, action, timestamp, and structured event
payload, but omit `tenant_id`.

Opportunity history accepts an optional exact `status` enum filter. Filtering remains
inside the tenant-scoped indexed query and works with the same bounded cursor contract;
an invalid status fails schema validation instead of being silently ignored.

The authenticated ECB reference-rate endpoint exposes the latest supported EUR quote
with its official source URL, retrieval/effective times, raw observation, confidence,
and explicit informational rate type. A bounded in-process cache (default one hour)
reduces upstream load. Upstream/network/format failure returns a stable `502` and is
never replaced by silently stale or invented data.

The authenticated provider registry exposes machine-readable scope, fixed hosts,
cache policy, limitations, enabled state, terms-review status, and its explicit approval
assertion. ECB can be disabled immediately with `TRADE_AGENT_ECB_ENABLED=false`;
disabled calls fail before constructing or contacting the provider. Production refuses
to start with ECB enabled unless `TRADE_AGENT_ECB_TERMS_APPROVED=true`. Set that flag
only after retaining the real authorization decision and completing the separate egress
review; it is not legal evidence by itself. No undocumented upstream rate-limit number
is asserted.

The authenticated ECB provider-health endpoint performs no network probe. It reports
only process-local observations from valid client-triggered cache misses: the last
attempt outcome, timezone-aware observation times, success/failure/consecutive-failure
counts, and cache hits. `NOT_OBSERVED` and `DISABLED` remain explicit states. Metrics
reset on process restart, cache hits do not revalidate ECB, and a successful last
attempt is not presented as a current-availability or SLA guarantee.

The evidence-bundle endpoint requires a version-matched `RUNNING` research run. It
calculates and persists evidence, price observations, point-in-time FX, all three
landed-cost scenarios, validation summary/issues, assumptions/unknowns, an immutable
report snapshot, and an audit event in one transaction. A result with warnings is
marked `NEEDS_VERIFICATION`; material conflicts are marked `NEEDS_HUMAN_REVIEW`
instead of being silently reported as complete.

The landed-cost-scenarios endpoint exposes the ordered calculation ledger rather than
requiring clients to parse Markdown. Every scenario includes total and per-unit
amounts plus each component's code, Persian label, amount, currency, evidence class,
and formula. It also returns the same deterministic scenario sensitivity used by the
latest-decision projection. Access is tenant-scoped and raw evidence bodies are omitted.

Each scenario may override the bundle-level `fx_rates` collection. Persisted rates are
linked to the exact landed-cost scenario that consumed them, so optimistic/base/
conservative FX assumptions remain historically reproducible. The run-level FX endpoint
returns the scenario name, pair, exact rate, rate type, effective/retrieval times,
source provenance, evidence class/confidence, and transformation without exposing raw
evidence bodies. Duplicate pair/type/effective-time identities inside one scenario are
rejected instead of relying on graph traversal order. New Persian reports include the
same scenario/rate/source lineage with escaped source labels and links.

Assumptions and unknowns are available as a tenant-scoped structured run snapshot and
are embedded in the latest-decision projection for result UI use. Notes must be
non-empty strings, are limited to 5,000 characters each and 200 per kind, and are
whitespace-normalized before persistence. Completed research runs remain immutable;
correction uses an idempotently created successor run with an explicit reason and
source-version check rather than history edits. The successor begins empty: old evidence,
calculations, and reports are never copied as current input. Its full corrected bundle
must pass the normal deterministic pipeline, and only a successor with a new immutable
report can become the latest decision. Run history exposes the predecessor link and
reason while audit metadata omits the reason's commercial text.

The supplier identity review queue is a bounded tenant-scoped projection of only
`UNREVIEWED` and `INCONCLUSIVE` offer-scoped claims. It folds the latest append-only
review, supports exact status filtering and keyset pagination, and includes opportunity
context plus source provenance for triage. Resolved claims leave the queue. Raw evidence,
review rationale, and reviewer identity are deliberately excluded, and queue membership
never means that a supplier identity is verified. Queue, history, and write access
require `SUPPLIER_IDENTITY_REVIEWER`.

The research review queue is a bounded tenant-scoped projection of report-bearing runs
whose current system-derived status is `NEEDS_VERIFICATION`, `NEEDS_HUMAN_REVIEW`, or
`PARTIAL`. It returns the exact expected version, report hash, validation policy/result,
confidence, opportunity context, and deterministic data-gap counts needed for triage.
Approval or rejection still uses the locked review endpoint. Report content, raw
evidence, declared-unknown text, review rationale, reviewer identity, and opportunity
notes are excluded from the queue. Queue, history, and write access require
`RESEARCH_REVIEWER`.

The run evidence catalog returns each deduplicated evidence record's source metadata,
classification, confidence, transformation, SHA-256 fingerprint, and deterministic
usage links to price observations or scenario FX inputs. It is tenant-scoped and omits
`raw_value`; the fingerprint supports integrity comparison without turning the general
decision endpoint into a raw-data export.

The price-observations endpoint provides the original commercial observation, quoted
quantity/unit/MOQ/Incoterm, payment terms/method, quote-valid-until timestamp, lead-time
days, product variant and attributes, market layer, source provenance, deterministic
product-match result, and normalized comparison price in one tenant-scoped view. The
normalized amount uses the BASE scenario FX path and remains a derived comparison value;
it does not overwrite or relabel the original price.

Quantity analysis groups observed quotes only within the same supplier, canonical
product identity, and normalized unit/currency group, orders them by quoted quantity,
and calculates exact `Decimal`
price changes between adjacent observed points. Anonymous suppliers are never merged.
The API and Persian report explicitly leave economic order range null/uncomputed until
demand, ordering, holding, lead-time, and service-level inputs are supplied.

Observed price distribution groups BASE-normalized unit prices only when canonical
product identity, quoted quantity, normalized unit/currency comparison group, and
declared market layer all match. It returns exact `Decimal` minimum, median, maximum,
range, observation IDs, and distinct source count. Missing-FX observations are listed
as excluded. A market-layer label does not establish Iranian-market representativeness,
source approval, or a validated benchmark.

The data-gaps endpoint combines only the run's persisted validation ledger and declared
unknown notes. It returns deterministic error/warning/unknown counts, the original
subject-linked issues, confidence/disposition context, and explicit limitations. It
does not claim that an empty recorded-gap set proves the research is commercially
complete, and gaps are closed only through verified evidence in a successor run.

Supplier coverage groups identified suppliers by their exact submitted name and reports
offer IDs, distinct source URLs, MOQ/Incoterm field coverage, rankable-offer count, and
the union of known unknown factors. Anonymous observations are listed separately and
never merged into a synthetic supplier. Every supplier remains `UNVERIFIED` because
offer metadata is not identity, certification, capacity, payment, or legal-status
evidence; distinct URLs also do not prove independent sources.

Evidence bundles may include bounded `supplier_identity_claims`. Each immutable claim
links an exact price-observation ID to a claimed legal name, jurisdiction, registration
number, and full source evidence in the same result transaction. The authenticated
claim projection omits raw evidence and begins at `UNREVIEWED`; it does not merge names
into a supplier profile, change ranking, or promote due diligence. An authenticated
append-only review ledger can record `EVIDENCE_SUPPORTED`, `EVIDENCE_CONTRADICTED`, or
`INCONCLUSIVE` under an expected-version row lock. These decisions describe support for
the scoped claim, never a verified supplier identity. Review history is tenant-scoped;
rationale stays out of audit payloads. Evidence usage and freshness counts include
claims, while the immutable generated report preserves the ingestion-time `UNREVIEWED`
snapshot and its escaped source fields.

The executive-summary endpoint exposes deterministic decision/recommendation codes,
all rank-1 offer candidates (including ties), their original and normalized price plus
source/evidence context, BASE landed cost per unit, confidence, and data-gap counts.
Candidates remain unverified and the output never authorizes a purchase. Until a
comparable Iranian benchmark has an approved provider contract, Iranian market price
and gross-spread amounts remain null with
`WITHHELD_NO_APPROVED_BENCHMARK` rather than being inferred from a market-layer label.

Trade-cost coverage reports the component codes recorded in every scenario, recognized
reference codes, reference codes not recorded, custom/unclassified codes, zero-amount
codes, and counts by evidence class. The reference vocabulary spans product, origin,
packaging, inspection, documentation, freight, insurance, tariff/tax, clearance,
payment/FX, sanctions, and domestic transport categories. An unrecorded code is not
automatically required or applicable, and the system never fills it with an estimate.

Incoterm coverage normalizes declared codes for grouping, identifies codes present in
the Incoterms 2020 reference vocabulary, lists unrecognized declarations and offers
with no declared code, and reports exact offer/supplier/source, named-place, version,
and complete-terms coverage. The original named place and declared version are retained
without assuming a default. Its comparison status remains
`WITHHELD_NO_INCOTERM_SCENARIOS`: the current model does not capture comparable route-
specific cost/control/risk scenarios, so the system does not recommend a “best”
Incoterm from offer metadata alone.

Evidence freshness reports each deduplicated item's retrieval time, exact age in seconds,
classification/confidence, fingerprint, provenance, and usage count against the stored
validation `evaluated_at`. It uses the same 30-day maximum age and five-minute future
clock tolerance as validation, with separate current, within-skew, stale, and future-
dated states. The projection is immutable with its run: it is not recalculated against
the wall clock, and freshness alone does not prove authority, accuracy, independence,
or commercial fitness.

Offer-terms coverage reports, for each retained observation, the exact presence or
absence of supplier identity, MOQ, product specification, Incoterm code, named place,
declared version, payment terms/method, quote validity, and lead-time days beside
rankability and the ranking ledger's unknown factors. Capacity, certifications, warranty,
and inspection terms are explicitly listed as outside the current schema. The endpoint
does not calculate a completeness percentage, verify a declared field, or infer whether
an uncaptured field is absent, required, or applicable. Expired quote validity becomes a
validation warning using the run's immutable evaluation time.

New Markdown reports encode all untrusted names, labels, notes, identifiers, and source
metadata before interpolation. Input newlines cannot create headings, HTML tags remain
text, Markdown control characters are escaped, and link targets are percent-encoded.
Previously persisted reports remain immutable; browser clients must still render every
report with an HTML-disabled or strictly sanitized Markdown policy.

Every evidence-bundle submission also requires an `Idempotency-Key` header containing
1–128 URL-safe identifier characters. An exact retry returns the original immutable
completion with `idempotency_replayed=true`; reusing the key for a different run body
returns `409 IDEMPOTENCY_CONFLICT`. The idempotency record is committed in the same
transaction as the research result.

Mutating HTTP requests are capped at 2,000,000 bytes by default, including chunked
requests without `Content-Length`; oversized requests receive `413 REQUEST_TOO_LARGE`.
The evidence parser also caps observations (500), each shared or scenario FX-rate
collection (100), scenarios (3),
costs per scenario (100), notes per kind (200, 5,000 characters each), and product
attributes (100).

Schema-validation failures return `422 REQUEST_VALIDATION_FAILED` with at most 50
safe details containing an allowlisted field location, validation type, and generic
message. Raw input, Pydantic context, and error URLs are never reflected; additional
errors are represented by an explicit omission marker.

Domain/parser failures use `422 INVALID_INPUT`. Only deliberately authored
`PublicInputError` messages may provide a specific safe reason; every other
`ValueError` is reduced to `request input is invalid`, so identifiers embedded in
invariant failures are not reflected to clients.

Every HTTP response uses `Cache-Control: no-store`, `Pragma: no-cache`,
`X-Content-Type-Options: nosniff`, deny framing/referrers, and disables browser device
permissions. `/api/v1` responses also vary on `X-API-Key`. HSTS belongs at the trusted
TLS edge and is not inferred from client-controlled forwarding headers.

Unexpected application/provider/database exceptions return a stable
`500 INTERNAL_ERROR` with the correlation ID and the same response-security headers.
Exception messages and classes are not exposed to clients; structured logs record only
the exception class plus method, path, and correlation—not the exception text.
