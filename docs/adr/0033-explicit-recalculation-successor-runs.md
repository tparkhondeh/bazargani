# ADR 0033: Explicit recalculation successor runs

## Decision

Correct an immutable research result by creating a new empty successor run, never by
patching or copying the predecessor's evidence, calculations, validation, or report.
Persist a self-referencing predecessor ID and a bounded normalized recalculation reason.
Expose both in tenant-scoped run history.

Require the source run's current version, an immutable source report, and an
`Idempotency-Key`. Canonically hash source ID, expected version, and normalized reason.
Under one transaction, lock the tenant-owned source run and insert the successor, a
minimal audit event, and the idempotency response. An identical retry returns the same
run; key reuse with a different request conflicts. Audit metadata records predecessor
and source version but not the reason text.

The successor starts at `CREATED` and follows the existing transition and full evidence-
bundle pipeline. Only after it receives its own report can it replace the predecessor in
the latest-decision projection. Multiple deliberate successors may branch from one
source; history remains explicit and no branch is selected without a report.

## Consequences

- Historical FX, evidence, calculations, report content, and report hashes never change.
- Stale values cannot become current merely because a correction run was opened.
- Retry ambiguity is bounded without mutating the predecessor version or status.
- This establishes lineage and full deterministic recalculation, not selective dependency
  recomputation; dependency graphs remain future work.
- Migration `20260901_0015` is additive and must pass PostgreSQL parity, native
  constraints, backup, and full rollback/re-upgrade gates before deployment.
