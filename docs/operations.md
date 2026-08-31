# Local Operations, Backup, and Recovery

## Development

Python 3.12+, PostgreSQL 17, and Docker Compose are the supported target. Start the
database, install the package, migrate, then run the loopback API:

```powershell
docker compose up -d postgres
python -m pip install -e ".[dev]"
$env:TRADE_AGENT_DATABASE_URL = "postgresql+psycopg://trade_agent:local-development-only@localhost:5432/trade_agent"
python -m alembic upgrade head
python -m trade_agent.api.run
```

SQLite auto-schema mode is allowed only for local development and tests. Production
requires PostgreSQL and Alembic (`TRADE_AGENT_AUTO_CREATE_SCHEMA=false`).

## Backup and restore baseline

Before production, implement encrypted `pg_dump --format=custom` backups to a
separate storage boundary, retention monitoring, and a monthly restore exercise.
Restore into a fresh database, run migrations/checks, compare row counts and critical
audit chains, then switch traffic only after approval. Never test restore over the
active production database.

RPO/RTO, encryption key ownership, retention period, and storage destination require
stakeholder approval. No production deployment is authorized until these are set.

## Production discovery (2026-08-31)

- `bazargani.wealthos.ir` returns HTTP 200 through MizbanCloud.
- `/home/wealthos/bazargani.wealthos.ir` exists but contains no application source.
- The active `wealthos-pr` PM2 application is `/home/wealthos/apps/pr` and belongs to
  the separate `pr.wealthos.ir` Personal Brand project; it must not be modified.
- Server Python 3.6 is below this project's requirement; deployment needs an isolated
  Python 3.12+ runtime/container or an approved alternate host setup.

