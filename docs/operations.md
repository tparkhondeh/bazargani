# Local Operations, Backup, and Recovery

## Development

Python 3.12+, PostgreSQL 17.11, and Docker Compose are the supported target. Start the
database, install the package, migrate, then run the loopback API:

```powershell
docker compose up -d postgres
python -m pip install -e ".[dev]"
$env:TRADE_AGENT_DATABASE_URL = "postgresql+psycopg://trade_agent:local-development-only@localhost:5432/trade_agent"
python -m alembic upgrade head
python -m trade_agent.api.run
```

Before a dependency change is committed, resolve and review the exact lock, update
`THIRD_PARTY_NOTICES.md`, and run the blocking compatibility/advisory checks:

```powershell
python -m pip install -r requirements.lock
python -m pip check
python -m pip_audit -r requirements.lock --strict --progress-spinner off
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

The value held in `$apiKey` is the only usable credential; transmit it once through
the selected secret channel. Credential values must be 32–128 characters. Tenant IDs
accept letters, digits, `_`, and `-`, up to 64 characters. A second credential can
map to the same tenant during rotation; deploy the new digest, move clients, then
remove the old digest.

Operational audit consumers should traverse `GET /api/v1/audit-events` with its
opaque `next_cursor`; never decode a cursor for authorization or request an unbounded
export. Correlate actions with `correlation_id` and treat review rationale as tenant
commercial data subject to the approved logging/retention policy.

`TRADE_AGENT_MAX_REQUEST_BODY_BYTES` defaults to `2000000` and is constrained to
1 KiB–10 MB. Configure the production reverse proxy to an equal or smaller body limit;
the application limit remains a required defense for direct/internal traffic.

Treat `422 REQUEST_VALIDATION_FAILED.details` as the client-safe debugging contract.
It is capped at 50 concrete issues plus an omission marker and intentionally does not
echo rejected values. Correlate server-side investigation by `correlation_id`; do not
add raw request bodies to application or proxy logs.

For `422 INVALID_INPUT`, only the explicit public-input error class may return a
specific reason. A generic `request input is invalid` can represent a rejected domain
invariant; investigate by correlation ID and never expose the underlying exception or
payload in a client-facing response.

The app marks all responses `no-store`/`no-cache` and sets anti-sniff/frame/referrer
and browser-permission headers. The TLS reverse proxy must independently set HSTS only
after HTTPS is correctly enforced for the approved domain; do not derive HSTS from an
untrusted `X-Forwarded-Proto` value. Preserve the app's headers on `401`, `413`, `422`,
`429`, and `503` responses.

`TRADE_AGENT_API_RATE_LIMIT_REQUESTS` defaults to `120` and is bounded to 1–100,000;
`TRADE_AGENT_API_RATE_LIMIT_WINDOW_SECONDS` defaults to `60` and is bounded to
1–3,600. This budget is per tenant **and per application process**. Configure a
trusted reverse proxy/shared limiter for the approved global tenant and source-IP
budgets; do not trust client-supplied forwarding headers inside the application.

`TRADE_AGENT_ECB_CACHE_TTL_SECONDS` defaults to `3600` and accepts 60–86,400 seconds.
The cache is per process; production egress/rate controls must still apply across all
workers. Monitor `502 UPSTREAM_UNAVAILABLE` without logging response bodies or
misrepresenting cached ECB reference rates as Iranian transaction rates.

SQLite auto-schema mode is allowed only for local development and tests. Production
requires PostgreSQL, Alembic (`TRADE_AGENT_AUTO_CREATE_SCHEMA=false`), and enabled
authentication. Migration `0007` assigns pre-existing rows to the quarantined
`legacy` tenant; reconcile those rows to approved tenants before issuing production
credentials, and back up the database before the migration.

Use `/health` only for process liveness and `/ready` for traffic admission. In managed
mode, readiness returns `200` only when database connectivity works and
`alembic_version` contains exactly the release revision; otherwise it returns a
correlation-preserving `503 NOT_READY` with `Retry-After: 5`. Do not route traffic on
health alone. Auto-create mode reports `schema_revision=unmanaged` and is never a
production readiness claim.

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
