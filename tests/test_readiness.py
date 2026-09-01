import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from trade_agent.api.app import create_app
from trade_agent.config import Settings
from trade_agent.infrastructure.database import Base
from trade_agent.infrastructure.readiness import (
    REQUIRED_SCHEMA_REVISION,
    ReadinessError,
    check_database_readiness,
)


def sqlite_engine():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


class DatabaseReadinessTests(unittest.TestCase):
    def test_required_revision_matches_the_alembic_head(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "migrations"))

        self.assertEqual(
            ScriptDirectory.from_config(config).get_current_head(),
            REQUIRED_SCHEMA_REVISION,
        )

    def test_auto_create_mode_checks_connectivity_without_claiming_a_revision(self) -> None:
        engine = sqlite_engine()
        Base.metadata.create_all(engine)

        result = check_database_readiness(engine, require_migration_head=False)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["schema_mode"], "auto-create")
        self.assertEqual(result["schema_revision"], "unmanaged")

    def test_managed_mode_requires_exactly_the_release_revision(self) -> None:
        engine = sqlite_engine()
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": REQUIRED_SCHEMA_REVISION},
            )

        result = check_database_readiness(engine, require_migration_head=True)

        self.assertEqual(result["schema_mode"], "alembic")
        self.assertEqual(result["schema_revision"], REQUIRED_SCHEMA_REVISION)

    def test_missing_or_stale_managed_schema_is_not_ready(self) -> None:
        missing = sqlite_engine()
        with self.assertRaisesRegex(ReadinessError, "readiness check failed"):
            check_database_readiness(missing, require_migration_head=True)

        stale = sqlite_engine()
        with stale.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('stale')")
            )
        with self.assertRaisesRegex(ReadinessError, "required migration revision"):
            check_database_readiness(stale, require_migration_head=True)

        multiple = sqlite_engine()
        with multiple.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES (:required), (:other)"
                ),
                {"required": REQUIRED_SCHEMA_REVISION, "other": "another-head"},
            )
        with self.assertRaisesRegex(ReadinessError, "required migration revision"):
            check_database_readiness(multiple, require_migration_head=True)

    def test_ready_endpoint_returns_stable_public_503_for_unmigrated_database(self) -> None:
        engine = sqlite_engine()
        settings = Settings(
            environment="test",
            database_url="sqlite+pysqlite://",
            auto_create_schema=False,
            log_level="CRITICAL",
        )

        with TestClient(create_app(settings=settings, engine=engine)) as client:
            health = client.get("/health")
            readiness = client.get(
                "/ready",
                headers={
                    "X-Correlation-ID": "343f80ba-1d47-4a56-aee5-901cbff70cb2",
                },
            )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(readiness.status_code, 503)
        self.assertEqual(readiness.headers["Retry-After"], "5")
        self.assertEqual(
            readiness.headers["X-Correlation-ID"],
            "343f80ba-1d47-4a56-aee5-901cbff70cb2",
        )
        self.assertEqual(readiness.json()["code"], "NOT_READY")
        self.assertNotIn("alembic_version", readiness.text)


if __name__ == "__main__":
    unittest.main()
