import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from trade_agent.api.app import create_app
from trade_agent.config import Settings
from trade_agent.infrastructure.database import AuditEventRecord


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        settings = Settings(
            environment="test",
            database_url="sqlite+pysqlite://",
            auto_create_schema=True,
            log_level="CRITICAL",
        )
        self.client_context = TestClient(create_app(settings=settings, engine=self.engine))
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)

    def test_opportunity_research_run_and_audit_flow(self) -> None:
        correlation_id = "343f80ba-1d47-4a56-aee5-901cbff70cb2"
        opportunity_response = self.client.post(
            "/api/v1/opportunities",
            headers={"X-Correlation-ID": correlation_id},
            json={
                "product_name": "اسپرسوساز نیمه‌اتوماتیک",
                "quantity": 2000,
                "target_market": "تهران",
            },
        )
        self.assertEqual(opportunity_response.status_code, 201)
        self.assertEqual(opportunity_response.headers["X-Correlation-ID"], correlation_id)
        opportunity = opportunity_response.json()

        run_response = self.client.post(f"/api/v1/opportunities/{opportunity['id']}/research-runs")
        self.assertEqual(run_response.status_code, 201)
        run = run_response.json()
        self.assertEqual(run["status"], "CREATED")
        self.assertEqual(run["version"], 1)

        transition_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        )
        self.assertEqual(transition_response.status_code, 200)
        self.assertEqual(transition_response.json()["version"], 2)

        with self.engine.connect() as connection:
            audit_count = connection.scalar(select(func.count()).select_from(AuditEventRecord))
        self.assertEqual(audit_count, 3)

    def test_optimistic_version_conflict_has_stable_error_contract(self) -> None:
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={"product_name": "Demo", "quantity": 1, "target_market": "Tehran"},
        ).json()
        run = self.client.post(f"/api/v1/opportunities/{opportunity['id']}/research-runs").json()

        response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 99},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "VERSION_CONFLICT")
        self.assertIn("correlation_id", response.json())


if __name__ == "__main__":
    unittest.main()
