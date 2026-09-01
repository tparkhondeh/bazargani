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

For authenticated local or staging operation, generate a random key, configure only
its SHA-256 digest, and send the original key as `X-API-Key`. Keep the raw key in an
approved secret manager, not in `.env`, shell history, source control, or logs.

```powershell
$apiKey = [Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()
$sha256 = [Security.Cryptography.SHA256]::Create()
$digest = [Convert]::ToHexString(
  $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($apiKey))
).ToLowerInvariant()
$env:TRADE_AGENT_AUTH_ENABLED = "true"
$env:TRADE_AGENT_API_KEY_CREDENTIALS = "{`"$digest`":`"tenant-name`"}"
```

The displayed `$apiKey` value is the only usable credential; transmit it once through
the selected secret channel. Credential values must be 32–128 characters. Tenant IDs
accept letters, digits, `_`, and `-`, up to 64 characters. A second credential can
map to the same tenant during rotation; deploy the new digest, move clients, then
remove the old digest.

`TRADE_AGENT_MAX_REQUEST_BODY_BYTES` defaults to `2000000` and is constrained to
1 KiB–10 MB. Configure the production reverse proxy to an equal or smaller body limit;
the application limit remains a required defense for direct/internal traffic.

SQLite auto-schema mode is allowed only for local development and tests. Production
requires PostgreSQL, Alembic (`TRADE_AGENT_AUTO_CREATE_SCHEMA=false`), and enabled
authentication. Migration `0007` assigns pre-existing rows to the quarantined
`legacy` tenant; reconcile those rows to approved tenants before issuing production
credentials, and back up the database before the migration.

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
