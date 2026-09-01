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
        self.assertEqual(readiness.json()["schema_revision"], "20260901_0010")

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

        latest_decision = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision"
        )
        self.assertEqual(latest_decision.status_code, 200)
        self.assertEqual(latest_decision.json()["research_run"]["id"], run["id"])
        self.assertEqual(
            latest_decision.json()["report"]["content_sha256"],
            completed["report_sha256"],
        )
        self.assertEqual(len(latest_decision.json()["scenarios"]), 3)

        cost_ledger = self.client.get(
            f"/api/v1/research-runs/{run['id']}/landed-cost-scenarios"
        )
        self.assertEqual(cost_ledger.status_code, 200)
        base_scenario = cost_ledger.json()["scenarios"][1]
        self.assertEqual(base_scenario["name"], "BASE")
        self.assertEqual(
            sum(Decimal(item["amount"]) for item in base_scenario["components"]),
            Decimal(base_scenario["total_amount"]),
        )
        self.assertEqual(
            cost_ledger.json()["scenario_sensitivity"]["status"],
            "COMPARABLE",
        )
        persisted_rates = self.client.get(
            f"/api/v1/research-runs/{run['id']}/fx-rates"
        )
        self.assertEqual(persisted_rates.status_code, 200)
        self.assertEqual(
            [item["scenario_name"] for item in persisted_rates.json()],
            ["OPTIMISTIC", "BASE", "CONSERVATIVE"],
        )
        decision_notes = self.client.get(
            f"/api/v1/research-runs/{run['id']}/assumptions"
        )
        self.assertEqual(decision_notes.status_code, 200)
        self.assertEqual(decision_notes.json()["assumptions"], bundle["assumptions"])
        self.assertEqual(latest_decision.json()["unknowns"], bundle["unknowns"])
        data_gaps = self.client.get(
            f"/api/v1/research-runs/{run['id']}/data-gaps"
        )
        self.assertEqual(data_gaps.status_code, 200)
        self.assertEqual(data_gaps.json()["status"], "GAPS_REQUIRE_VERIFICATION")
        self.assertEqual(
            data_gaps.json()["declared_unknown_count"],
            len(bundle["unknowns"]),
        )
        self.assertEqual(
            data_gaps.json()["issue_count"],
            completed["validation_issue_count"],
        )
        self.assertNotIn("raw_value", json.dumps(data_gaps.json()))
        evidence_catalog = self.client.get(
            f"/api/v1/research-runs/{run['id']}/evidence"
        )
        self.assertEqual(evidence_catalog.status_code, 200)
        self.assertEqual(len(evidence_catalog.json()), completed["evidence_count"])
        self.assertNotIn("raw_value", json.dumps(evidence_catalog.json()))
        price_observations = self.client.get(
            f"/api/v1/research-runs/{run['id']}/price-observations"
        )
        self.assertEqual(price_observations.status_code, 200)
        self.assertEqual(len(price_observations.json()), completed["price_observation_count"])
        self.assertEqual(price_observations.json()[0]["normalized_currency"], "IRR")
        quantity_analysis = self.client.get(
            f"/api/v1/research-runs/{run['id']}/quantity-analysis"
        )
        self.assertEqual(quantity_analysis.status_code, 200)
        self.assertEqual(quantity_analysis.json()["status"], "OBSERVED_QUOTES_ONLY")
        self.assertIsNone(quantity_analysis.json()["economic_order_range_min"])
        price_distribution = self.client.get(
            f"/api/v1/research-runs/{run['id']}/price-distribution"
        )
        self.assertEqual(price_distribution.status_code, 200)
        distribution = price_distribution.json()
        self.assertEqual(distribution["status"], "OBSERVED_DISTRIBUTIONS")
        self.assertEqual(len(distribution["groups"]), 1)
        self.assertEqual(distribution["groups"][0]["observation_count"], 1)
        self.assertEqual(
            Decimal(distribution["groups"][0]["median_amount"]),
            Decimal("500"),
        )
        self.assertNotIn("raw_value", json.dumps(distribution))
        supplier_coverage = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-coverage"
        )
        self.assertEqual(supplier_coverage.status_code, 200)
        self.assertEqual(
            supplier_coverage.json()["status"],
            "SUPPLIER_EVIDENCE_COVERAGE",
        )
        self.assertEqual(supplier_coverage.json()["suppliers"][0]["offer_count"], 1)
        self.assertEqual(
            supplier_coverage.json()["suppliers"][0]["due_diligence_status"],
            "UNVERIFIED",
        )
        self.assertNotIn("raw_value", json.dumps(supplier_coverage.json()))

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
