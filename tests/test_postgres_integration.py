import hashlib
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select

from trade_agent.api.app import create_app
from trade_agent.config import Settings
from trade_agent.infrastructure.database import (
    AuditEventRecord,
    IdempotencyRecord,
    LandedCostScenarioRecord,
    OpportunityRecord,
    ResearchReviewRecord,
)

POSTGRES_URL = os.getenv("TRADE_AGENT_TEST_POSTGRES_URL")


@unittest.skipUnless(POSTGRES_URL, "TRADE_AGENT_TEST_POSTGRES_URL is not configured")
class PostgreSQLIntegrationTests(unittest.TestCase):
    api_key = "postgres-integration-key-000000000001"

    @classmethod
    def setUpClass(cls) -> None:
        assert POSTGRES_URL is not None
        cls.engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
        settings = Settings(
            environment="test",
            database_url=POSTGRES_URL,
            auto_create_schema=False,
            log_level="CRITICAL",
            auth_enabled=True,
            api_key_credentials={
                hashlib.sha256(cls.api_key.encode()).hexdigest(): "postgres-ci",
            },
        )
        cls.client_context = TestClient(create_app(settings=settings, engine=cls.engine))
        cls.client = cls.client_context.__enter__()
        cls.client.headers.update({"X-API-Key": cls.api_key})

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_full_research_transaction_uses_postgresql_types_and_tenant_scope(self) -> None:
        readiness = self.client.get("/ready")
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["schema_mode"], "alembic")
        self.assertEqual(readiness.json()["schema_revision"], "20260901_0009")

        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        opportunity_response = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": bundle["product_name"],
                "quantity": bundle["quantity"],
                "target_market": bundle["destination"],
            },
        )
        self.assertEqual(opportunity_response.status_code, 201)
        opportunity = opportunity_response.json()

        context_update = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            json={
                "expected_version": 1,
                "next_action": "Request factory quotation",
                "deadline": "2026-09-15T09:00:00Z",
                "notes": "PostgreSQL workflow context",
            },
        )
        self.assertEqual(context_update.status_code, 200)
        self.assertEqual(context_update.json()["version"], 2)
        self.assertEqual(context_update.json()["deadline"], "2026-09-15T09:00:00Z")

        opportunity_transition = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/transitions",
            json={"target_status": "SOURCING", "expected_version": 2},
        )
        self.assertEqual(opportunity_transition.status_code, 200)
        self.assertEqual(opportunity_transition.json()["status"], "SOURCING")
        self.assertEqual(opportunity_transition.json()["version"], 3)

        run_response = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        )
        self.assertEqual(run_response.status_code, 201)
        run = run_response.json()
        running = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        ).json()

        completed_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "postgres-ci-completion"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        self.assertEqual(completed_response.status_code, 200)
        completed = completed_response.json()
        self.assertEqual(completed["status"], "NEEDS_VERIFICATION")

        replay = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "postgres-ci-completion"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["idempotency_replayed"])

        review = self.client.post(
            f"/api/v1/research-runs/{run['id']}/reviews",
            json={
                "decision": "APPROVE",
                "rationale": "PostgreSQL integration review approval",
                "expected_version": completed["version"],
            },
        )
        self.assertEqual(review.status_code, 201)
        self.assertEqual(review.json()["resulting_status"], "COMPLETED")

        additional_ids = {
            self.client.post(
                "/api/v1/opportunities",
                json={
                    "product_name": f"PostgreSQL page item {index}",
                    "quantity": index,
                    "target_market": "Tehran",
                },
            ).json()["id"]
            for index in (1, 2)
        }
        opportunity_ids = {opportunity["id"], *additional_ids}
        first_page = self.client.get(
            "/api/v1/opportunities",
            params={"limit": 2},
        ).json()
        second_page = self.client.get(
            "/api/v1/opportunities",
            params={"limit": 2, "after": first_page["next_cursor"]},
        ).json()
        paged_ids = {
            item["id"] for item in (*first_page["items"], *second_page["items"])
        }
        self.assertEqual(paged_ids, opportunity_ids)
        self.assertIsNone(second_page["next_cursor"])

        audit_ids: list[str] = []
        audit_cursor: str | None = None
        while True:
            params: dict[str, int | str] = {"limit": 3}
            if audit_cursor is not None:
                params["after"] = audit_cursor
            audit_page_response = self.client.get("/api/v1/audit-events", params=params)
            self.assertEqual(audit_page_response.status_code, 200)
            audit_page = audit_page_response.json()
            audit_ids.extend(event["id"] for event in audit_page["items"])
            audit_cursor = audit_page["next_cursor"]
            if audit_cursor is None:
                break
        self.assertEqual(len(audit_ids), len(set(audit_ids)))

        with self.engine.connect() as connection:
            tenant_id = connection.scalar(
                select(OpportunityRecord.tenant_id).where(
                    OpportunityRecord.id == opportunity["id"]
                )
            )
            total = connection.scalar(
                select(LandedCostScenarioRecord.total_amount)
                .where(LandedCostScenarioRecord.research_run_id == run["id"])
                .order_by(LandedCostScenarioRecord.name)
                .limit(1)
            )
            audit_payload = connection.scalar(
                select(AuditEventRecord.payload)
                .where(AuditEventRecord.aggregate_id == run["id"])
                .order_by(AuditEventRecord.occurred_at.desc())
                .limit(1)
            )
            audit_count = connection.scalar(
                select(func.count())
                .select_from(AuditEventRecord)
                .where(AuditEventRecord.tenant_id == "postgres-ci")
            )
            idempotency_count = connection.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.tenant_id == "postgres-ci")
            )
            review_count = connection.scalar(
                select(func.count())
                .select_from(ResearchReviewRecord)
                .where(ResearchReviewRecord.tenant_id == "postgres-ci")
            )

        self.assertEqual(tenant_id, "postgres-ci")
        self.assertIsInstance(total, Decimal)
        self.assertIsInstance(audit_payload, dict)
        self.assertEqual(len(audit_ids), audit_count)
        self.assertEqual(idempotency_count, 1)
        self.assertEqual(review_count, 1)


if __name__ == "__main__":
    unittest.main()
