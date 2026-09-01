# Third-party dependency inventory

Snapshot: 2026-09-01. This is an engineering inventory, not legal advice. Preserve
upstream copyright/license notices in distributions and repeat review before release.

| Direct package | Version | Declared license | Purpose |
|---|---:|---|---|
| Alembic | 1.19.1 | MIT | Database migrations |
| FastAPI | 0.141.1 | MIT | HTTP delivery layer |
| Psycopg / Psycopg Binary | 3.3.4 | LGPL-3.0-only | PostgreSQL driver |
| Pydantic Settings | 2.15.0 | MIT | Validated configuration |
| SQLAlchemy | 2.0.52 | MIT | Persistence mapping and transactions |
| Uvicorn | 0.52.4 | BSD-3-Clause | ASGI server |
| HTTPX | 0.28.1 | BSD-3-Clause | Safe outbound HTTP and API test client |
| Mypy | 1.20.2 | MIT | Development type checking |
| pip-audit | 2.10.1 | Apache-2.0 | Dependency vulnerability audit |
| Ruff | 0.16.5 | MIT | Development lint/format |

Transitive packages and exact versions are listed in `requirements.lock`. The
LGPL-licensed Psycopg binary distribution is dynamically used as an unmodified
library; packaging and source-offer obligations require legal confirmation before
commercial distribution. Production may choose system `libpq` plus `psycopg` after
deployment review.
