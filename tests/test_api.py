import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from trade_agent.api.app import create_app
from trade_agent.config import Settings
from trade_agent.infrastructure.database import (
    AuditEventRecord,
    DecisionReportRecord,
    EvidenceRecord,
    FXRateRecord,
    LandedCostScenarioRecord,
    PriceObservationRecord,
)


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

    def test_parse_request_returns_only_critical_questions(self) -> None:
        response = self.client.post(
            "/api/v1/requests/parse",
            json={"text": "۳۰۰ دستگاه پمپ آب به شیراز"},
        )

        self.assertEqual(response.status_code, 200)
        parsed = response.json()
        self.assertTrue(parsed["can_start_research"])
        self.assertEqual(parsed["quantity"], 300)
        self.assertEqual(parsed["destination"], "شیراز")
        self.assertEqual(parsed["critical_questions"], [])
        self.assertEqual(len(parsed["assumptions"]), 1)

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

    def test_bundle_is_calculated_persisted_and_reported_atomically(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": bundle["product_name"],
                "quantity": bundle["quantity"],
                "target_market": bundle["destination"],
            },
        ).json()
        run = self.client.post(f"/api/v1/opportunities/{opportunity['id']}/research-runs").json()
        running = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        ).json()

        completed_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            json={"expected_version": running["version"], "bundle": bundle},
        )

        self.assertEqual(completed_response.status_code, 200)
        completed = completed_response.json()
        self.assertEqual(completed["status"], "COMPLETED")
        self.assertEqual(completed["evidence_count"], 2)
        self.assertEqual(completed["price_observation_count"], 1)
        self.assertEqual(completed["fx_rate_count"], 1)
        self.assertEqual(completed["scenario_count"], 3)

        report_response = self.client.get(f"/api/v1/research-runs/{run['id']}/report")
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("گزارش تصمیم بازرگانی", report_response.json()["content"])
        self.assertEqual(report_response.json()["content_sha256"], completed["report_sha256"])

        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(EvidenceRecord)), 2)
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(PriceObservationRecord)),
                1,
            )
            self.assertEqual(connection.scalar(select(func.count()).select_from(FXRateRecord)), 1)
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(LandedCostScenarioRecord)),
                3,
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(DecisionReportRecord)),
                1,
            )

    def test_bundle_mismatch_rolls_back_all_results(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": "محصول متفاوت",
                "quantity": bundle["quantity"],
                "target_market": bundle["destination"],
            },
        ).json()
        run = self.client.post(f"/api/v1/opportunities/{opportunity['id']}/research-runs").json()
        self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        )

        response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            json={"expected_version": 2, "bundle": bundle},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_INPUT")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(EvidenceRecord)), 0)


if __name__ == "__main__":
    unittest.main()
