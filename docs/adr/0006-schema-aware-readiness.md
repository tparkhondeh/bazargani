# ADR 0006: Schema-aware database readiness

## Decision

Keep `/health` as a public process-liveness signal. Make `/ready` verify database
connectivity and, whenever schema auto-creation is disabled, require exactly the
Alembic head shipped with the application release. Missing, stale, or multiple
revision rows return a stable public `503 NOT_READY` with `Retry-After` and no database
error details.

The application carries the required revision as a release constant. A test compares
that constant with Alembic's actual single head, so adding a migration without updating
the readiness contract fails CI. Local/test auto-create mode reports its schema as
`unmanaged` and never claims Alembic parity.

## Consequences

- Orchestration cannot route production traffic to code running against a stale schema.
- Liveness remains independent of a temporary database outage, avoiding unnecessary
  process restarts while readiness removes the instance from service.
- The check is read-only and exposes only the expected release revision after success.
- A future multi-head migration design must explicitly change both the check and ADR.
