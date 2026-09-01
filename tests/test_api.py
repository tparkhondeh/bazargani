import hashlib
import json
import unittest
from datetime import datetime
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
    IdempotencyRecord,
    LandedCostScenarioRecord,
    OpportunityRecord,
    PriceObservationRecord,
    ProductMatchRecord,
    ResearchReviewRecord,
    ResearchRunRecord,
    ResearchValidationRecord,
    SupplierOfferRankingRecord,
    ValidationIssueRecord,
)


class ApiTests(unittest.TestCase):
    api_key = "tenant-a-test-key-0000000000000001"
    other_api_key = "tenant-b-test-key-0000000000000002"

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
            auth_enabled=True,
            api_key_credentials={
                hashlib.sha256(self.api_key.encode()).hexdigest(): "tenant-a",
                hashlib.sha256(self.other_api_key.encode()).hexdigest(): "tenant-b",
            },
        )
        self.client_context = TestClient(create_app(settings=settings, engine=self.engine))
        self.client = self.client_context.__enter__()
        self.client.headers.update({"X-API-Key": self.api_key})

        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)

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
            opportunity_tenant = connection.scalar(
                select(OpportunityRecord.tenant_id).where(
                    OpportunityRecord.id == opportunity["id"]
                )
            )
            run_tenant = connection.scalar(
                select(ResearchRunRecord.tenant_id).where(ResearchRunRecord.id == run["id"])
            )
            audit_boundaries = connection.execute(
                select(AuditEventRecord.tenant_id, AuditEventRecord.actor_id)
            ).all()
        self.assertEqual(audit_count, 3)
        self.assertEqual(opportunity_tenant, "tenant-a")
        self.assertEqual(run_tenant, "tenant-a")
        self.assertEqual({item.tenant_id for item in audit_boundaries}, {"tenant-a"})
        self.assertTrue(all(item.actor_id.startswith("api-key:") for item in audit_boundaries))

    def test_health_is_public_but_api_requires_a_valid_key(self) -> None:
        health = self.client.get("/health", headers={"X-API-Key": ""})
        missing = self.client.post(
            "/api/v1/requests/parse",
            headers={"X-API-Key": ""},
            json={"text": "100 pumps to Tehran"},
        )
        invalid = self.client.post(
            "/api/v1/requests/parse",
            headers={"X-API-Key": "x" * 32},
            json={"text": "100 pumps to Tehran"},
        )

        self.assertEqual(health.status_code, 200)
        for response in (missing, invalid):
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["code"], "AUTHENTICATION_REQUIRED")
            self.assertEqual(response.headers["WWW-Authenticate"], "ApiKey")
            self.assertIn("correlation_id", response.json())

    def test_openapi_declares_api_key_security_on_protected_routes(self) -> None:
        document = self.client.get("/openapi.json").json()

        scheme = document["components"]["securitySchemes"]["APIKeyHeader"]
        self.assertEqual(scheme, {"type": "apiKey", "in": "header", "name": "X-API-Key"})
        self.assertEqual(
            document["paths"]["/api/v1/opportunities"]["post"]["security"],
            [{"APIKeyHeader": []}],
        )
        self.assertNotIn("security", document["paths"]["/health"]["get"])

    def test_tenant_cannot_read_or_mutate_another_tenants_aggregate(self) -> None:
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={"product_name": "Pump", "quantity": 10, "target_market": "Tehran"},
        ).json()
        run = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        ).json()
        other_headers = {"X-API-Key": self.other_api_key}

        opportunity_read = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}",
            headers=other_headers,
        )
        run_create = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs",
            headers=other_headers,
        )
        run_transition = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            headers=other_headers,
            json={"target_status": "RUNNING", "expected_version": 1},
        )
        result_reads = [
            self.client.get(
                f"/api/v1/research-runs/{run['id']}/{resource}",
                headers=other_headers,
            )
            for resource in (
                "report",
                "validation",
                "product-matches",
                "supplier-offer-rankings",
            )
        ]

        for response in (opportunity_read, run_create, run_transition, *result_reads):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "NOT_FOUND")

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

    def test_review_outcome_requires_an_atomic_tenant_scoped_decision(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": bundle["product_name"],
                "quantity": bundle["quantity"],
                "target_market": bundle["destination"],
            },
        ).json()
        run = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        ).json()
        running = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        ).json()
        completed = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "review-flow-result"},
            json={"expected_version": running["version"], "bundle": bundle},
        ).json()
        self.assertEqual(completed["status"], "NEEDS_VERIFICATION")

        bypass = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={
                "target_status": "COMPLETED",
                "expected_version": completed["version"],
            },
        )
        wrong_version = self.client.post(
            f"/api/v1/research-runs/{run['id']}/reviews",
            json={
                "decision": "APPROVE",
                "rationale": "منابع و فرضیات توسط بازبین بررسی شد.",
                "expected_version": 99,
            },
        )
        cross_tenant = self.client.post(
            f"/api/v1/research-runs/{run['id']}/reviews",
            headers={"X-API-Key": self.other_api_key},
            json={
                "decision": "APPROVE",
                "rationale": "cross-tenant attempt",
                "expected_version": completed["version"],
            },
        )

        self.assertEqual(bypass.status_code, 409)
        self.assertEqual(bypass.json()["code"], "INVALID_TRANSITION")
        self.assertEqual(wrong_version.status_code, 409)
        self.assertEqual(wrong_version.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(cross_tenant.status_code, 404)

        approval = self.client.post(
            f"/api/v1/research-runs/{run['id']}/reviews",
            json={
                "decision": "APPROVE",
                "rationale": "منابع و فرضیات توسط بازبین بررسی شد.",
                "expected_version": completed["version"],
            },
        )
        self.assertEqual(approval.status_code, 201)
        decision = approval.json()
        self.assertEqual(decision["previous_status"], "NEEDS_VERIFICATION")
        self.assertEqual(decision["resulting_status"], "COMPLETED")
        self.assertEqual(decision["resulting_version"], completed["version"] + 1)
        self.assertTrue(decision["reviewer_actor_id"].startswith("api-key:"))

        reviews = self.client.get(f"/api/v1/research-runs/{run['id']}/reviews")
        hidden_reviews = self.client.get(
            f"/api/v1/research-runs/{run['id']}/reviews",
            headers={"X-API-Key": self.other_api_key},
        )
        self.assertEqual(reviews.status_code, 200)
        retrieved_decisions = reviews.json()
        self.assertEqual(len(retrieved_decisions), 1)
        retrieved = retrieved_decisions[0]
        for field in (
            "id",
            "research_run_id",
            "reviewer_actor_id",
            "decision",
            "rationale",
            "previous_status",
            "resulting_status",
            "previous_version",
            "resulting_version",
        ):
            self.assertEqual(retrieved[field], decision[field])
        datetime.fromisoformat(retrieved["created_at"].replace("Z", "+00:00"))
        self.assertEqual(hidden_reviews.status_code, 404)

        with self.engine.connect() as connection:
            persisted_run = connection.execute(
                select(ResearchRunRecord.status, ResearchRunRecord.version).where(
                    ResearchRunRecord.id == run["id"]
                )
            ).one()
            persisted_review_tenant = connection.scalar(
                select(ResearchReviewRecord.tenant_id).where(
                    ResearchReviewRecord.research_run_id == run["id"]
                )
            )
        self.assertEqual(persisted_run.status, "COMPLETED")
        self.assertEqual(persisted_run.version, completed["version"] + 1)
        self.assertEqual(persisted_review_tenant, "tenant-a")

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
            headers={"Idempotency-Key": "demo-bundle-completion"},
            json={"expected_version": running["version"], "bundle": bundle},
        )

        self.assertEqual(completed_response.status_code, 200)
        completed = completed_response.json()
        self.assertFalse(completed["idempotency_replayed"])
        self.assertEqual(completed["status"], "NEEDS_VERIFICATION")
        self.assertEqual(completed["validation_disposition"], "NEEDS_VERIFICATION")
        self.assertGreater(completed["validation_issue_count"], 0)
        self.assertLess(completed["confidence_score"], 100)
        self.assertEqual(completed["evidence_count"], 2)
        self.assertEqual(completed["price_observation_count"], 1)
        self.assertEqual(completed["product_match_count"], 1)
        self.assertEqual(completed["supplier_ranking_count"], 1)
        self.assertEqual(completed["fx_rate_count"], 1)
        self.assertEqual(completed["scenario_count"], 3)

        replay_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "demo-bundle-completion"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        self.assertEqual(replay_response.status_code, 200)
        replayed = replay_response.json()
        self.assertTrue(replayed["idempotency_replayed"])
        self.assertEqual(replayed["version"], completed["version"])
        self.assertEqual(replayed["report_sha256"], completed["report_sha256"])

        conflicting_bundle = json.loads(json.dumps(bundle, ensure_ascii=False))
        conflicting_bundle["metadata"]["retry_payload_changed"] = True
        conflict_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "demo-bundle-completion"},
            json={"expected_version": running["version"], "bundle": conflicting_bundle},
        )
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(conflict_response.json()["code"], "IDEMPOTENCY_CONFLICT")

        invalid_conflict_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "demo-bundle-completion"},
            json={"expected_version": running["version"], "bundle": {}},
        )
        self.assertEqual(invalid_conflict_response.status_code, 409)
        self.assertEqual(
            invalid_conflict_response.json()["code"],
            "IDEMPOTENCY_CONFLICT",
        )

        report_response = self.client.get(f"/api/v1/research-runs/{run['id']}/report")
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("گزارش تصمیم بازرگانی", report_response.json()["content"])
        self.assertEqual(report_response.json()["content_sha256"], completed["report_sha256"])

        validation_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/validation"
        )
        self.assertEqual(validation_response.status_code, 200)
        validation = validation_response.json()
        self.assertEqual(validation["disposition"], "NEEDS_VERIFICATION")
        self.assertEqual(len(validation["issues"]), completed["validation_issue_count"])
        self.assertIn("ASSUMED_COST_COMPONENTS", {item["code"] for item in validation["issues"]})
        self.assertIn(
            "SUPPLIER_DUE_DILIGENCE_REQUIRED",
            {item["code"] for item in validation["issues"]},
        )
        self.assertIn(
            "INSUFFICIENT_SUPPLIER_COMPARISON",
            {item["code"] for item in validation["issues"]},
        )

        matches_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/product-matches"
        )
        self.assertEqual(matches_response.status_code, 200)
        matches = matches_response.json()
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["classification"], "EXACT_VARIANT")
        self.assertEqual(matches[0]["score"], 100)
        self.assertEqual(matches[0]["requested_attributes"], {"variant": "DEMO"})
        self.assertEqual(matches[0]["observed_attributes"], {"variant": "DEMO"})

        ranking_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-offer-rankings"
        )
        self.assertEqual(ranking_response.status_code, 200)
        rankings = ranking_response.json()
        self.assertEqual(len(rankings), 1)
        self.assertEqual(rankings[0]["rank"], 1)
        self.assertEqual(rankings[0]["normalized_currency"], "IRR")
        self.assertIn("supplier_reliability", rankings[0]["unknown_factors"])

        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(EvidenceRecord)), 2)
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(PriceObservationRecord)),
                1,
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(ProductMatchRecord)),
                1,
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(SupplierOfferRankingRecord)),
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
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(ResearchValidationRecord)),
                1,
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(ValidationIssueRecord)),
                completed["validation_issue_count"],
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(IdempotencyRecord)),
                1,
            )
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(AuditEventRecord)),
                4,
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
            headers={"Idempotency-Key": "mismatched-product"},
            json={"expected_version": 2, "bundle": bundle},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_INPUT")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(EvidenceRecord)), 0)

    def test_bundle_missing_explicit_unit_has_validation_error_contract(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        del bundle["observations"][0]["unit"]
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": bundle["product_name"],
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
            headers={"Idempotency-Key": "missing-unit"},
            json={"expected_version": 2, "bundle": bundle},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_INPUT")
        self.assertIn("unit", response.json()["message"])

    def test_bundle_destination_mismatch_rolls_back_results(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": bundle["product_name"],
                "quantity": bundle["quantity"],
                "target_market": "شیراز",
            },
        ).json()
        run = self.client.post(f"/api/v1/opportunities/{opportunity['id']}/research-runs").json()
        self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        )

        response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "mismatched-destination"},
            json={"expected_version": 2, "bundle": bundle},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("destination", response.json()["message"])
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(select(func.count()).select_from(EvidenceRecord)), 0)

    def test_evidence_bundle_requires_idempotency_key(self) -> None:
        response = self.client.post(
            "/api/v1/research-runs/not-used/evidence-bundle",
            json={"expected_version": 1, "bundle": {}},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "REQUEST_VALIDATION_FAILED")

    def test_oversized_request_is_rejected_with_stable_contract(self) -> None:
        correlation_id = "343f80ba-1d47-4a56-aee5-901cbff70cb2"
        response = self.client.post(
            "/api/v1/requests/parse",
            headers={"X-Correlation-ID": correlation_id},
            json={"text": "x" * 2_100_000},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "REQUEST_TOO_LARGE")
        self.assertEqual(response.json()["correlation_id"], correlation_id)
        self.assertEqual(response.headers["X-Correlation-ID"], correlation_id)


if __name__ == "__main__":
    unittest.main()
