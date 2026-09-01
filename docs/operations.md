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

`TRADE_AGENT_MAX_REQUEST_BODY_BYTES` defaults to `2000000` and is constrained to
1 KiB–10 MB. Configure the production reverse proxy to an equal or smaller body limit;
the application limit remains a required defense for direct/internal traffic.

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

Idempotency records currently follow research-result retention. Before production,
approve a minimum retry window and a cleanup job that never removes keys while clients
may still retry; monitor uniqueness conflicts and replay volume without logging raw
bundle content.

## Production discovery (2026-08-31)

- `bazargani.wealthos.ir` returns HTTP 200 through MizbanCloud.
- `/home/wealthos/bazargani.wealthos.ir` exists but contains no application source.
- The active `wealthos-pr` PM2 application is `/home/wealthos/apps/pr` and belongs to
  the separate `pr.wealthos.ir` Personal Brand project; it must not be modified.
- Server Python 3.6 is below this project's requirement; deployment needs an isolated
  Python 3.12+ runtime/container or an approved alternate host setup.
