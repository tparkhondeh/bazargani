from __future__ import annotations

from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

REQUIRED_SCHEMA_REVISION = "20260901_0008"


class DatabaseReadiness(TypedDict):
    status: str
    persistence: str
    schema_mode: str
    schema_revision: str


class ReadinessError(RuntimeError):
    pass


def check_database_readiness(
    engine: Engine,
    *,
    require_migration_head: bool,
) -> DatabaseReadiness:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if not require_migration_head:
                return {
                    "status": "ready",
                    "persistence": "database",
                    "schema_mode": "auto-create",
                    "schema_revision": "unmanaged",
                }
            revisions = tuple(
                connection.scalars(text("SELECT version_num FROM alembic_version"))
            )
    except SQLAlchemyError:
        raise ReadinessError("database readiness check failed") from None

    if revisions != (REQUIRED_SCHEMA_REVISION,):
        raise ReadinessError("database schema is not at the required migration revision")
    return {
        "status": "ready",
        "persistence": "database",
        "schema_mode": "alembic",
        "schema_revision": REQUIRED_SCHEMA_REVISION,
    }
