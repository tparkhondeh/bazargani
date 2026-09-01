# Data Model

The calculation core uses immutable domain objects. PostgreSQL persistence is managed
with Alembic; SQLite is permitted only for local/test execution.

Planned core tables: `opportunities`, `research_runs`, `products`,
`product_variants`, `suppliers`, `sources`, `evidence`, `price_observations`,
`quotes`, `quantity_tiers`, `fx_rates`, `landed_cost_scenarios`,
`landed_cost_components`, `assumptions`, `recommendations`, and `audit_events`.

Rules:

- UUID primary keys; `timestamptz` in UTC; explicit created/retrieved/effective time.
- Foreign keys are enforced and domain enums use check constraints.
- Unique evidence fingerprint prevents duplicate ingestion per research run.
- Observations and rates are append-only; corrections create superseding rows.
- Index research run, opportunity, source, retrieval time, product fingerprint, and
  supplier identity. Add indexes only from measured query plans.
- Persist decimal amounts as bounded `numeric`, never float.
- Backup target before production: daily encrypted backup, tested monthly restore;
  final RPO/RTO awaits stakeholder approval.

Implemented migrations now persist opportunities, versioned research runs, audit
events, sources, deduplicated evidence, price observations, point-in-time FX rates,
landed-cost scenario/component ledgers, assumptions/unknowns, and immutable Markdown
report snapshots. Report hashes and append-only result semantics make a completed run
reproducible and prevent silent overwrite.

Migration `20260831_0003` adds explicit price units plus one immutable validation
summary and its issue ledger per research run. The summary records policy version,
evaluation time, disposition, and a 0–100 confidence score; each issue records its
stable code, severity, subject, Persian explanation, and structured details.

Migration `20260831_0004` stores raw requested/observed product attributes and one
policy-versioned match result for every retained price observation. Match rows retain
the class, score, normalized-name similarity, matched/conflicting/missing feature
keys, and Persian explanations; normalized features never overwrite raw attributes.

Migration `20260831_0005` adds one immutable supplier-offer ranking per retained
price observation. It stores quantity eligibility, comparison group, normalized
price, rankability/rank, every score component, unresolved diligence factors,
explanations, and policy version. This is an offer score, not an unsupported supplier
trust score.

Migration `20260831_0006` adds `idempotency_records`, uniquely keyed by operation
scope and client key. It stores only the canonical request hash and immutable response
payload, not a duplicate raw evidence bundle. Result and idempotency writes share one
transaction so a failed result cannot leave a false successful replay marker.

Migration `20260831_0007` adds `tenant_id` to opportunities, research runs, audit
events, and idempotency records, plus `actor_id` on audit events. Repository aggregate
access always resolves through the tenant-owned opportunity/run. Existing rows are
backfilled into a quarantined `legacy` tenant for explicit reconciliation rather than
being discarded or silently assigned to a live customer.

Migration `20260901_0008` adds the append-only `research_reviews` ledger. Each record
stores tenant, research run, reviewer actor fingerprint, `APPROVE`/`REJECT` decision,
required rationale, previous/resulting status, consecutive versions, and creation
time. The decision and research-run status/version change are committed with the
corresponding audit event in one transaction.

Migration `20260901_0009` adds nullable `next_action`, timezone-aware `deadline`, and
`notes` columns to opportunities. They are mutable workflow context protected by the
aggregate's existing optimistic version; audit payloads retain changed field names and
the resulting version without duplicating commercial values.

Migration `20260901_0010` adds a required scenario foreign key to each FX-rate row and
changes uniqueness from run-level to scenario-level pair/type/effective time. Existing
shared rate rows are expanded across their three historical scenarios during upgrade.
New writes preserve different rate values and provenance per scenario; the downgrade
collapses scenario multiplicity because the legacy schema cannot represent it.

Migration `20260901_0011` adds nullable `incoterm_named_place` and
`incoterm_version` columns to price observations. Existing rows remain null instead of
receiving an invented place or edition. New domain inputs normalize safe whitespace and
case for the code while retaining the submitted named place and version as distinct
immutable terms; downgrade removes only these two additive fields.

Migration `20260901_0012` adds nullable `payment_terms`, `payment_method`, timezone-aware
`quote_valid_until`, and positive `lead_time_days` columns to price observations. Legacy
rows remain null and therefore unknown. The fields retain the exact offer/evidence
relationship; they do not create a mutable supplier profile or a default commercial
contract, and downgrade removes only the additive fields and lead-time constraint.

Migration `20260901_0013` adds immutable `supplier_identity_claims`. Each row belongs to
one research run, exact price observation, and evidence record; the external claim ID is
unique within the run. Required legal name, jurisdiction, and registration number are
stored as the source's assertion, not a normalized supplier master record. Claim
evidence participates in the existing fingerprint, usage, freshness, and raw-body
protection rules. The claim has no mutable or verified status column.

Migration `20260901_0014` adds append-only `supplier_identity_claim_reviews`. Each row
records tenant/run/claim scope, credential actor fingerprint, one bounded rationale,
the previous and resulting evidence-review states, consecutive versions, and creation
time. The database enforces allowed non-verified decisions, status/decision agreement,
one-version increments, initial `UNREVIEWED` semantics, and uniqueness per claim/version.
The live claim projection folds the latest ledger row; the immutable decision report
continues to represent the ingestion-time snapshot.

Migration `20260901_0015` adds nullable `supersedes_research_run_id` and
`recalculation_reason` to research runs. Existing and independently created runs keep
both null. A successor must set both, reference another run, and cannot reference itself;
the repository additionally enforces same tenant/opportunity and a report-bearing source.
An index supports predecessor-to-successor history. Result tables remain linked only to
their own run, so lineage never aliases or copies evidence, scenarios, or reports.

The supplier identity review queue adds no table. It joins tenant-owned research runs to
claims, source/offer context, and a grouped maximum review version, then filters the
effective state to `UNREVIEWED` or `INCONCLUSIVE`. Pagination uses the immutable claim
`(created_at, id)` pair; concurrent reviews can change membership between HTTP pages.

The append-only audit ledger is exposed through a bounded tenant-scoped keyset query
ordered by `(occurred_at, id)`. API views omit the redundant tenant identifier while
retaining actor fingerprint, correlation ID, aggregate, action, structured payload,
and occurrence time. The tenant predicate is applied independently on every page.
