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
