# Data Model

The first slice uses immutable in-memory domain objects and JSON fixtures. Phase 2
adds PostgreSQL with Alembic migrations.

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

