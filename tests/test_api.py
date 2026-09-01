import hashlib
import json
import unittest
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from trade_agent.api.app import create_app
from trade_agent.config import Settings
from trade_agent.domain.models import Confidence, Evidence, EvidenceClass, FXRate
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
    SupplierIdentityClaimRecord,
    SupplierIdentityClaimReviewRecord,
    SupplierOfferRankingRecord,
    ValidationIssueRecord,
)
from trade_agent.providers.errors import ProviderUnavailableError


class StubReferenceRateProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def latest_reference_rate(self, quote_currency: str) -> FXRate:
        self.calls += 1
        currency = quote_currency.strip().upper()
        if currency == "EUR" or len(currency) != 3:
            raise ValueError("quote currency must be a non-EUR three-letter code")
        if self.fail:
            raise ProviderUnavailableError("ECB reference-rate service is unavailable")
        return FXRate(
            base_currency="EUR",
            quote_currency=currency,
            rate=Decimal("1.1802"),
            evidence=Evidence(
                classification=EvidenceClass.FACT,
                source_name="European Central Bank Data Portal",
                source_url="https://data-api.ecb.europa.eu/service/data/EXR/test",
                retrieved_at=datetime(2026, 9, 1, 8, tzinfo=UTC),
                raw_value='{"OBS_VALUE":"1.1802","TIME_PERIOD":"2026-08-31"}',
                confidence=Confidence.HIGH,
                transformation="ECB contract fixture",
            ),
            rate_type="ECB_DAILY_REFERENCE_INFORMATIONAL",
            effective_at=datetime(2026, 8, 31, tzinfo=UTC),
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
        self.reference_rates = StubReferenceRateProvider()
        self.client_context = TestClient(
            create_app(
                settings=settings,
                engine=self.engine,
                reference_rates=self.reference_rates,
            )
        )
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

    def test_opportunity_transition_is_versioned_audited_and_tenant_scoped(self) -> None:
        correlation_id = "22feb8c4-15ac-4f78-aeab-1d673ee80a30"
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={"product_name": "Pump", "quantity": 10, "target_market": "Tehran"},
        ).json()

        transitioned = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/transitions",
            headers={"X-Correlation-ID": correlation_id},
            json={"target_status": "SOURCING", "expected_version": 1},
        )
        stale = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/transitions",
            json={"target_status": "NEGOTIATING", "expected_version": 1},
        )
        invalid = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/transitions",
            json={"target_status": "WON", "expected_version": 2},
        )
        hidden = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/transitions",
            headers={"X-API-Key": self.other_api_key},
            json={"target_status": "NEGOTIATING", "expected_version": 2},
        )

        self.assertEqual(transitioned.status_code, 200)
        self.assertEqual(transitioned.headers["X-Correlation-ID"], correlation_id)
        self.assertEqual(transitioned.json()["status"], "SOURCING")
        self.assertEqual(transitioned.json()["version"], 2)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(invalid.status_code, 409)
        self.assertEqual(invalid.json()["code"], "INVALID_TRANSITION")
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json()["code"], "NOT_FOUND")

        with self.engine.connect() as connection:
            event = connection.execute(
                select(
                    AuditEventRecord.tenant_id,
                    AuditEventRecord.actor_id,
                    AuditEventRecord.correlation_id,
                    AuditEventRecord.payload,
                ).where(
                    AuditEventRecord.aggregate_id == opportunity["id"],
                    AuditEventRecord.action == "STATUS_CHANGED",
                )
            ).one()
        key_fingerprint = hashlib.sha256(self.api_key.encode()).hexdigest()[:12]
        self.assertEqual(event.tenant_id, "tenant-a")
        self.assertEqual(event.actor_id, f"api-key:{key_fingerprint}")
        self.assertEqual(event.correlation_id, correlation_id)
        self.assertEqual(
            event.payload,
            {"from": "RESEARCHING", "to": "SOURCING", "version": 2},
        )

    def test_opportunity_context_is_partial_versioned_and_redacted_from_audit(self) -> None:
        commercial_note = "private supplier target is 91.25 USD"
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={"product_name": "Pump", "quantity": 10, "target_market": "Tehran"},
        ).json()

        updated = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            json={
                "expected_version": 1,
                "next_action": "  Request verified quotation  ",
                "deadline": "2026-09-15T12:30:00+03:30",
                "notes": commercial_note,
            },
        )
        cleared = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            json={"expected_version": 2, "notes": None},
        )
        stale = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            json={"expected_version": 1, "next_action": "Stale overwrite"},
        )
        empty = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            json={"expected_version": 3},
        )
        naive_deadline = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            json={"expected_version": 3, "deadline": "2026-09-16T10:00:00"},
        )
        hidden = self.client.patch(
            f"/api/v1/opportunities/{opportunity['id']}/context",
            headers={"X-API-Key": self.other_api_key},
            json={"expected_version": 3, "next_action": "Cross-tenant overwrite"},
        )
        persisted = self.client.get(f"/api/v1/opportunities/{opportunity['id']}")

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["next_action"], "Request verified quotation")
        self.assertEqual(updated.json()["deadline"], "2026-09-15T09:00:00Z")
        self.assertEqual(updated.json()["notes"], commercial_note)
        self.assertEqual(updated.json()["version"], 2)
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["next_action"], "Request verified quotation")
        self.assertIsNone(cleared.json()["notes"])
        self.assertEqual(cleared.json()["version"], 3)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(empty.json()["code"], "INVALID_INPUT")
        self.assertEqual(naive_deadline.status_code, 422)
        self.assertEqual(naive_deadline.json()["code"], "REQUEST_VALIDATION_FAILED")
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(persisted.status_code, 200)
        self.assertEqual(persisted.json()["deadline"], "2026-09-15T09:00:00Z")

        with self.engine.connect() as connection:
            payloads = sorted(
                connection.scalars(
                    select(AuditEventRecord.payload).where(
                        AuditEventRecord.aggregate_id == opportunity["id"],
                        AuditEventRecord.action == "CONTEXT_UPDATED",
                    )
                ),
                key=lambda payload: payload["version"],
            )
        self.assertEqual(
            payloads,
            [
                {"fields": ["deadline", "next_action", "notes"], "version": 2},
                {"fields": ["notes"], "version": 3},
            ],
        )
        self.assertNotIn(commercial_note, json.dumps(payloads))

    def test_latest_opportunity_decision_is_evidence_backed_and_preserves_ties(self) -> None:
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": "محصول آزمایشی — داده ساختگی",
                "quantity": 10,
                "target_market": "تهران",
            },
        ).json()
        missing = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision"
        )

        run = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        ).json()
        running = self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        ).json()
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        bundle["case_id"] = "LATEST-DECISION-TIE"
        tied_observation = deepcopy(bundle["observations"][0])
        tied_observation["observation_id"] = "demo-price-2"
        tied_observation["supplier_name"] = "Demo Supplier Two — NOT REAL"
        tied_observation["evidence"]["source_name"] = "Second synthetic source"
        tied_observation["evidence"]["source_url"] = "https://example.com/demo-supplier-two"
        tied_observation["evidence"]["raw_value"] = "Second synthetic test value: 5 USD"
        bundle["observations"].append(tied_observation)
        completed = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "latest-opportunity-decision"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        self.assertEqual(completed.status_code, 200)

        newer_empty_run = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        )
        self.assertEqual(newer_empty_run.status_code, 201)
        decision = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision"
        )
        hidden = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision",
            headers={"X-API-Key": self.other_api_key},
        )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["code"], "NOT_FOUND")
        self.assertEqual(decision.status_code, 200)
        body = decision.json()
        self.assertEqual(body["opportunity_id"], opportunity["id"])
        self.assertEqual(body["research_run"]["id"], run["id"])
        self.assertNotEqual(body["research_run"]["id"], newer_empty_run.json()["id"])
        self.assertEqual(body["report"]["case_id"], "LATEST-DECISION-TIE")
        self.assertEqual(
            [scenario["name"] for scenario in body["scenarios"]],
            ["OPTIMISTIC", "BASE", "CONSERVATIVE"],
        )
        self.assertEqual(body["scenario_sensitivity"]["status"], "COMPARABLE")
        self.assertEqual(body["scenario_sensitivity"]["base_per_unit"], "630.00000000")
        self.assertEqual(
            body["scenario_sensitivity"]["range_percent_of_base"],
            "25.51",
        )
        self.assertEqual(body["assumptions"], bundle["assumptions"])
        self.assertEqual(body["unknowns"], bundle["unknowns"])
        self.assertEqual(
            {offer["supplier_name"] for offer in body["leading_offers"]},
            {"Demo Supplier — NOT REAL", "Demo Supplier Two — NOT REAL"},
        )
        self.assertTrue(all(offer["rank"] == 1 for offer in body["leading_offers"]))
        self.assertEqual(
            {offer["source_url"] for offer in body["leading_offers"]},
            {
                "https://example.com/demo-supplier",
                "https://example.com/demo-supplier-two",
            },
        )
        self.assertTrue(
            all("raw_value" not in offer for offer in body["leading_offers"])
        )
        executive = body["executive_summary"]
        self.assertEqual(executive["decision_status"], "VERIFICATION_REQUIRED")
        self.assertEqual(
            executive["supplier_candidate_status"],
            "MULTIPLE_LEADING_UNVERIFIED_CANDIDATES",
        )
        self.assertEqual(
            {item["supplier_name"] for item in executive["leading_supplier_candidates"]},
            {"Demo Supplier — NOT REAL", "Demo Supplier Two — NOT REAL"},
        )
        self.assertEqual(Decimal(executive["base_landed_cost_per_unit"]), Decimal("630"))
        self.assertEqual(
            executive["iran_market_benchmark_status"],
            "WITHHELD_NO_APPROVED_BENCHMARK",
        )
        self.assertIsNone(executive["potential_gross_spread_per_unit"])
        self.assertNotIn("raw_value", json.dumps(executive))
        self.assertNotIn("tenant_id", decision.text)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json()["code"], "NOT_FOUND")

    def test_recalculation_creates_an_idempotent_successor_without_mutating_history(
        self,
    ) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        opportunity = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": bundle["product_name"],
                "quantity": bundle["quantity"],
                "target_market": bundle["destination"],
            },
        ).json()
        source = self.client.post(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        ).json()
        successor_path = f"/api/v1/research-runs/{source['id']}/successors"
        no_idempotency_key = self.client.post(
            successor_path,
            json={"expected_version": 1, "reason": "Correct a cost assumption"},
        )
        blank_reason = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "recalculation-blank-reason"},
            json={"expected_version": 1, "reason": "   "},
        )
        no_result = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "recalculation-before-result"},
            json={"expected_version": 1, "reason": "Correct a cost assumption"},
        )
        self.assertEqual(no_idempotency_key.status_code, 422)
        self.assertEqual(blank_reason.status_code, 422)
        self.assertEqual(blank_reason.json()["code"], "INVALID_INPUT")
        self.assertEqual(no_result.status_code, 409)
        self.assertEqual(no_result.json()["code"], "INVALID_TRANSITION")

        running = self.client.post(
            f"/api/v1/research-runs/{source['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": source["version"]},
        ).json()
        completed = self.client.post(
            f"/api/v1/research-runs/{source['id']}/evidence-bundle",
            headers={"Idempotency-Key": "recalculation-source-result"},
            json={"expected_version": running["version"], "bundle": bundle},
        ).json()
        source_report_before = self.client.get(
            f"/api/v1/research-runs/{source['id']}/report"
        ).json()
        reason = "Correct the synthetic freight assumption from 1000 to 1100 IRR"
        request_body = {
            "expected_version": completed["version"],
            "reason": f"  {reason}  ",
        }
        successor = self.client.post(
            successor_path,
            headers={
                "Idempotency-Key": "recalculation-successor-1",
                "X-Correlation-ID": "806d584e-b7a0-45e5-acf9-0271e7b9a1d8",
            },
            json=request_body,
        )
        replay = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "recalculation-successor-1"},
            json={"expected_version": completed["version"], "reason": reason},
        )
        conflict = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "recalculation-successor-1"},
            json={**request_body, "reason": "A different correction"},
        )
        stale = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "recalculation-stale-version"},
            json={"expected_version": completed["version"] - 1, "reason": reason},
        )
        hidden = self.client.post(
            successor_path,
            headers={
                "Idempotency-Key": "recalculation-other-tenant",
                "X-API-Key": self.other_api_key,
            },
            json=request_body,
        )

        self.assertEqual(successor.status_code, 201)
        successor_body = successor.json()
        self.assertEqual(successor_body["status"], "CREATED")
        self.assertEqual(successor_body["version"], 1)
        self.assertEqual(successor_body["opportunity_id"], opportunity["id"])
        self.assertEqual(successor_body["supersedes_research_run_id"], source["id"])
        self.assertEqual(successor_body["recalculation_reason"], reason)
        self.assertFalse(successor_body["idempotency_replayed"])
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()["id"], successor_body["id"])
        self.assertTrue(replay.json()["idempotency_replayed"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(
            self.client.get(
                f"/api/v1/research-runs/{successor_body['id']}/report"
            ).status_code,
            404,
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    select(func.count())
                    .select_from(EvidenceRecord)
                    .where(EvidenceRecord.research_run_id == successor_body["id"])
                ),
                0,
            )
            self.assertEqual(
                connection.scalar(
                    select(func.count())
                    .select_from(DecisionReportRecord)
                    .where(DecisionReportRecord.research_run_id == successor_body["id"])
                ),
                0,
            )

        run_history = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/research-runs"
        ).json()["items"]
        history_by_id = {item["id"]: item for item in run_history}
        self.assertIsNone(history_by_id[source["id"]]["supersedes_research_run_id"])
        self.assertIsNone(history_by_id[source["id"]]["recalculation_reason"])
        self.assertEqual(
            history_by_id[successor_body["id"]]["supersedes_research_run_id"],
            source["id"],
        )
        latest_before_recalculation = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision"
        ).json()
        self.assertEqual(latest_before_recalculation["research_run"]["id"], source["id"])

        successor_running = self.client.post(
            f"/api/v1/research-runs/{successor_body['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        ).json()
        corrected_bundle = deepcopy(bundle)
        corrected_bundle["case_id"] = "DEMO-EXPLICIT-RECALCULATION"
        corrected_bundle["assumptions"].append(reason)
        for scenario in corrected_bundle["scenarios"]:
            scenario["costs"][0]["money"]["amount"] = "1100"
        corrected = self.client.post(
            f"/api/v1/research-runs/{successor_body['id']}/evidence-bundle",
            headers={"Idempotency-Key": "recalculation-corrected-result"},
            json={
                "expected_version": successor_running["version"],
                "bundle": corrected_bundle,
            },
        )
        self.assertEqual(corrected.status_code, 200)
        corrected_report = self.client.get(
            f"/api/v1/research-runs/{successor_body['id']}/report"
        ).json()
        source_report_after = self.client.get(
            f"/api/v1/research-runs/{source['id']}/report"
        ).json()
        latest_after_recalculation = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision"
        ).json()
        self.assertNotEqual(
            corrected_report["content_sha256"],
            source_report_before["content_sha256"],
        )
        self.assertEqual(
            source_report_after["content_sha256"],
            source_report_before["content_sha256"],
        )
        self.assertEqual(
            latest_after_recalculation["research_run"]["id"],
            successor_body["id"],
        )
        self.assertEqual(
            latest_after_recalculation["research_run"]["supersedes_research_run_id"],
            source["id"],
        )

        with self.engine.connect() as connection:
            lineage = connection.execute(
                select(
                    ResearchRunRecord.supersedes_research_run_id,
                    ResearchRunRecord.recalculation_reason,
                ).where(ResearchRunRecord.id == successor_body["id"])
            ).one()
            recalculation_audit = connection.execute(
                select(
                    AuditEventRecord.correlation_id,
                    AuditEventRecord.payload,
                ).where(
                    AuditEventRecord.aggregate_id == successor_body["id"],
                    AuditEventRecord.action == "CREATED_AS_RECALCULATION",
                )
            ).one()
            idempotency_count = connection.scalar(
                select(func.count()).select_from(IdempotencyRecord)
            )
        self.assertEqual(lineage.supersedes_research_run_id, source["id"])
        self.assertEqual(lineage.recalculation_reason, reason)
        self.assertEqual(
            recalculation_audit.correlation_id,
            "806d584e-b7a0-45e5-acf9-0271e7b9a1d8",
        )
        self.assertEqual(
            recalculation_audit.payload,
            {
                "supersedes_research_run_id": source["id"],
                "source_version": completed["version"],
            },
        )
        self.assertNotIn(reason, json.dumps(recalculation_audit.payload))
        self.assertEqual(idempotency_count, 3)

    def test_health_is_public_but_api_requires_a_valid_key(self) -> None:
        health = self.client.get("/health", headers={"X-API-Key": ""})
        readiness = self.client.get("/ready", headers={"X-API-Key": ""})
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
        self.assertEqual(readiness.status_code, 200)
        self.assertEqual(readiness.json()["schema_mode"], "auto-create")
        self.assertEqual(readiness.json()["schema_revision"], "unmanaged")
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
                "data-gaps",
                "landed-cost-scenarios",
                "cost-coverage",
                "fx-rates",
                "assumptions",
                "evidence",
                "evidence-freshness",
                "price-observations",
                "incoterm-coverage",
                "offer-terms-coverage",
                "quantity-analysis",
                "price-distribution",
                "product-matches",
                "supplier-offer-rankings",
                "supplier-coverage",
                "supplier-identity-claims",
                "executive-summary",
            )
        ]

        for response in (opportunity_read, run_create, run_transition, *result_reads):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "NOT_FOUND")

    def test_tenant_history_uses_bounded_cursor_pagination(self) -> None:
        created = [
            self.client.post(
                "/api/v1/opportunities",
                json={
                    "product_name": f"Product {index}",
                    "quantity": index,
                    "target_market": "Tehran",
                },
            ).json()
            for index in range(1, 4)
        ]
        other = self.client.post(
            "/api/v1/opportunities",
            headers={"X-API-Key": self.other_api_key},
            json={"product_name": "Other", "quantity": 1, "target_market": "Shiraz"},
        ).json()

        first_page = self.client.get("/api/v1/opportunities", params={"limit": 2})
        self.assertEqual(first_page.status_code, 200)
        first = first_page.json()
        self.assertEqual(len(first["items"]), 2)
        self.assertIsNotNone(first["next_cursor"])
        second_page = self.client.get(
            "/api/v1/opportunities",
            params={"limit": 2, "after": first["next_cursor"]},
        )
        self.assertEqual(second_page.status_code, 200)
        second = second_page.json()
        self.assertEqual(len(second["items"]), 1)
        self.assertIsNone(second["next_cursor"])
        listed_ids = [item["id"] for item in (*first["items"], *second["items"])]
        self.assertEqual(set(listed_ids), {item["id"] for item in created})
        self.assertEqual(len(listed_ids), len(set(listed_ids)))
        self.assertNotIn(other["id"], listed_ids)

        other_page = self.client.get(
            "/api/v1/opportunities",
            headers={"X-API-Key": self.other_api_key},
        ).json()
        self.assertEqual([item["id"] for item in other_page["items"]], [other["id"]])

        runs = [
            self.client.post(
                f"/api/v1/opportunities/{created[0]['id']}/research-runs"
            ).json()
            for _ in range(3)
        ]
        run_first = self.client.get(
            f"/api/v1/opportunities/{created[0]['id']}/research-runs",
            params={"limit": 2},
        ).json()
        run_second = self.client.get(
            f"/api/v1/opportunities/{created[0]['id']}/research-runs",
            params={"limit": 2, "after": run_first["next_cursor"]},
        ).json()
        listed_run_ids = [
            item["id"] for item in (*run_first["items"], *run_second["items"])
        ]
        self.assertEqual(set(listed_run_ids), {item["id"] for item in runs})
        self.assertEqual(len(listed_run_ids), len(set(listed_run_ids)))
        self.assertIsNone(run_second["next_cursor"])

        hidden_runs = self.client.get(
            f"/api/v1/opportunities/{created[0]['id']}/research-runs",
            headers={"X-API-Key": self.other_api_key},
        )
        malformed = self.client.get(
            "/api/v1/opportunities",
            params={"after": "not-a-cursor"},
        )
        excessive_limit = self.client.get(
            "/api/v1/opportunities",
            params={"limit": 101},
        )
        self.assertEqual(hidden_runs.status_code, 404)
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(malformed.json()["code"], "INVALID_INPUT")
        self.assertEqual(excessive_limit.status_code, 422)
        self.assertEqual(excessive_limit.json()["code"], "REQUEST_VALIDATION_FAILED")

    def test_opportunity_history_can_be_filtered_by_tenant_owned_status(self) -> None:
        created = [
            self.client.post(
                "/api/v1/opportunities",
                json={
                    "product_name": f"Filtered product {index}",
                    "quantity": index,
                    "target_market": "Tehran",
                },
            ).json()
            for index in range(1, 5)
        ]
        for opportunity in created[:2]:
            response = self.client.post(
                f"/api/v1/opportunities/{opportunity['id']}/transitions",
                json={"target_status": "SOURCING", "expected_version": 1},
            )
            self.assertEqual(response.status_code, 200)
        other = self.client.post(
            "/api/v1/opportunities",
            headers={"X-API-Key": self.other_api_key},
            json={"product_name": "Hidden sourcing", "quantity": 1, "target_market": "Shiraz"},
        ).json()
        self.client.post(
            f"/api/v1/opportunities/{other['id']}/transitions",
            headers={"X-API-Key": self.other_api_key},
            json={"target_status": "SOURCING", "expected_version": 1},
        )

        sourcing = self.client.get(
            "/api/v1/opportunities",
            params={"status": "SOURCING"},
        )
        first_researching = self.client.get(
            "/api/v1/opportunities",
            params={"status": "RESEARCHING", "limit": 1},
        ).json()
        second_researching = self.client.get(
            "/api/v1/opportunities",
            params={
                "status": "RESEARCHING",
                "limit": 1,
                "after": first_researching["next_cursor"],
            },
        ).json()
        invalid = self.client.get(
            "/api/v1/opportunities",
            params={"status": "sourcing"},
        )

        self.assertEqual(sourcing.status_code, 200)
        self.assertEqual(
            {item["id"] for item in sourcing.json()["items"]},
            {item["id"] for item in created[:2]},
        )
        research_ids = {
            first_researching["items"][0]["id"],
            second_researching["items"][0]["id"],
        }
        self.assertEqual(research_ids, {item["id"] for item in created[2:]})
        self.assertIsNotNone(first_researching["next_cursor"])
        self.assertIsNone(second_researching["next_cursor"])
        self.assertNotIn(other["id"], research_ids)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["code"], "REQUEST_VALIDATION_FAILED")

    def test_audit_history_is_paginated_and_tenant_scoped(self) -> None:
        created = [
            self.client.post(
                "/api/v1/opportunities",
                json={
                    "product_name": f"Audited product {index}",
                    "quantity": index,
                    "target_market": "Tehran",
                },
            ).json()
            for index in range(1, 4)
        ]
        other = self.client.post(
            "/api/v1/opportunities",
            headers={"X-API-Key": self.other_api_key},
            json={"product_name": "Other tenant", "quantity": 1, "target_market": "Shiraz"},
        ).json()

        first_response = self.client.get("/api/v1/audit-events", params={"limit": 2})
        self.assertEqual(first_response.status_code, 200)
        first = first_response.json()
        self.assertEqual(len(first["items"]), 2)
        self.assertIsNotNone(first["next_cursor"])
        second = self.client.get(
            "/api/v1/audit-events",
            params={"limit": 2, "after": first["next_cursor"]},
        ).json()
        self.assertEqual(len(second["items"]), 1)
        self.assertIsNone(second["next_cursor"])

        events = [*first["items"], *second["items"]]
        self.assertEqual(
            {event["aggregate_id"] for event in events},
            {item["id"] for item in created},
        )
        self.assertEqual(len({event["id"] for event in events}), 3)
        key_fingerprint = hashlib.sha256(self.api_key.encode()).hexdigest()[:12]
        expected_actor = f"api-key:{key_fingerprint}"
        for event in events:
            self.assertEqual(event["actor_id"], expected_actor)
            self.assertEqual(event["aggregate_type"], "Opportunity")
            self.assertEqual(event["action"], "CREATED")
            self.assertNotIn("tenant_id", event)

        other_page = self.client.get(
            "/api/v1/audit-events",
            headers={"X-API-Key": self.other_api_key},
        ).json()
        self.assertEqual(
            [event["aggregate_id"] for event in other_page["items"]],
            [other["id"]],
        )

        malformed = self.client.get(
            "/api/v1/audit-events",
            params={"after": "not-a-cursor"},
        )
        excessive_limit = self.client.get(
            "/api/v1/audit-events",
            params={"limit": 101},
        )
        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(malformed.json()["code"], "INVALID_INPUT")
        self.assertEqual(excessive_limit.status_code, 422)
        self.assertEqual(excessive_limit.json()["code"], "REQUEST_VALIDATION_FAILED")

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

    def test_ecb_reference_rate_preserves_provenance_and_stable_errors(self) -> None:
        unauthenticated = self.client.get(
            "/api/v1/reference-rates/ecb/USD",
            headers={"X-API-Key": ""},
        )
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(self.reference_rates.calls, 0)

        response = self.client.get("/api/v1/reference-rates/ecb/usd")

        self.assertEqual(response.status_code, 200)
        rate = response.json()
        self.assertEqual(rate["base_currency"], "EUR")
        self.assertEqual(rate["quote_currency"], "USD")
        self.assertEqual(rate["rate"], "1.1802")
        self.assertEqual(rate["rate_type"], "ECB_DAILY_REFERENCE_INFORMATIONAL")
        self.assertEqual(rate["evidence"]["classification"], "FACT")
        self.assertEqual(
            rate["evidence"]["source_name"],
            "European Central Bank Data Portal",
        )
        self.assertIn("TIME_PERIOD", rate["evidence"]["raw_value"])

        invalid = self.client.get("/api/v1/reference-rates/ecb/EUR")
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["code"], "INVALID_INPUT")

        self.reference_rates.fail = True
        unavailable = self.client.get("/api/v1/reference-rates/ecb/GBP")
        self.assertEqual(unavailable.status_code, 502)
        self.assertEqual(unavailable.json()["code"], "UPSTREAM_UNAVAILABLE")
        self.assertIn("correlation_id", unavailable.json())

    def test_provider_registry_is_authenticated_and_ecb_has_a_kill_switch(self) -> None:
        unauthenticated = self.client.get(
            "/api/v1/providers",
            headers={"X-API-Key": ""},
        )
        catalog_response = self.client.get("/api/v1/providers")

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(catalog_response.status_code, 200)
        catalog = catalog_response.json()
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["id"], "ecb-fx-reference")
        self.assertTrue(catalog[0]["enabled"])
        self.assertEqual(catalog[0]["retrieval_method"], "OFFICIAL_API")
        self.assertEqual(catalog[0]["terms_review_status"], "PENDING_FORMAL_REVIEW")
        self.assertFalse(catalog[0]["terms_approved"])
        self.assertEqual(catalog[0]["fixed_hosts"], ["data-api.ecb.europa.eu"])
        self.assertIsNone(catalog[0]["declared_rate_limit"])

        disabled_engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        disabled_rates = StubReferenceRateProvider()
        disabled_settings = Settings(
            environment="test",
            database_url="sqlite+pysqlite://",
            auto_create_schema=True,
            log_level="CRITICAL",
            ecb_enabled=False,
            auth_enabled=True,
            api_key_credentials={
                hashlib.sha256(self.api_key.encode()).hexdigest(): "tenant-a",
            },
        )
        with TestClient(
            create_app(
                settings=disabled_settings,
                engine=disabled_engine,
                reference_rates=disabled_rates,
            )
        ) as disabled_client:
            disabled_client.headers.update({"X-API-Key": self.api_key})
            disabled_catalog = disabled_client.get("/api/v1/providers")
            disabled_health = disabled_client.get(
                "/api/v1/providers/ecb-fx-reference/health"
            )
            disabled_rate = disabled_client.get("/api/v1/reference-rates/ecb/USD")

        self.assertFalse(disabled_catalog.json()[0]["enabled"])
        self.assertEqual(disabled_health.json()["status"], "DISABLED")
        self.assertFalse(disabled_health.json()["endpoint_probe_performed"])
        self.assertEqual(disabled_health.json()["upstream_attempt_count"], 0)
        self.assertEqual(disabled_rate.status_code, 502)
        self.assertEqual(disabled_rate.json()["code"], "UPSTREAM_UNAVAILABLE")
        self.assertEqual(disabled_rates.calls, 0)

        approved_engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        approved_settings = Settings(
            environment="test",
            database_url="sqlite+pysqlite://",
            auto_create_schema=True,
            log_level="CRITICAL",
            ecb_terms_approved=True,
            auth_enabled=True,
            api_key_credentials={
                hashlib.sha256(self.api_key.encode()).hexdigest(): "tenant-a",
            },
        )
        with TestClient(
            create_app(
                settings=approved_settings,
                engine=approved_engine,
                reference_rates=StubReferenceRateProvider(),
            )
        ) as approved_client:
            approved_client.headers.update({"X-API-Key": self.api_key})
            approved_catalog = approved_client.get("/api/v1/providers").json()

        self.assertTrue(approved_catalog[0]["terms_approved"])
        self.assertEqual(approved_catalog[0]["terms_review_status"], "APPROVED")

    def test_provider_health_reports_observed_calls_without_network_probes(self) -> None:
        path = "/api/v1/providers/ecb-fx-reference/health"
        unauthenticated = self.client.get(path, headers={"X-API-Key": ""})
        initial = self.client.get(path)

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["status"], "NOT_OBSERVED")
        self.assertEqual(initial.json()["observation_scope"], "PROCESS_LOCAL")
        self.assertFalse(initial.json()["endpoint_probe_performed"])
        self.assertEqual(initial.json()["upstream_attempt_count"], 0)
        self.assertEqual(self.reference_rates.calls, 0)

        self.assertEqual(
            self.client.get("/api/v1/reference-rates/ecb/USD").status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/v1/reference-rates/ecb/usd").status_code,
            200,
        )
        observed = self.client.get(path).json()

        self.assertEqual(observed["status"], "LAST_ATTEMPT_SUCCEEDED")
        self.assertEqual(observed["upstream_attempt_count"], 1)
        self.assertEqual(observed["success_count"], 1)
        self.assertEqual(observed["failure_count"], 0)
        self.assertEqual(observed["cache_hit_count"], 1)
        self.assertEqual(self.reference_rates.calls, 1)

        self.reference_rates.fail = True
        self.assertEqual(
            self.client.get("/api/v1/reference-rates/ecb/GBP").status_code,
            502,
        )
        failed = self.client.get(path).json()
        self.assertEqual(failed["status"], "LAST_ATTEMPT_FAILED")
        self.assertEqual(failed["upstream_attempt_count"], 2)
        self.assertEqual(failed["success_count"], 1)
        self.assertEqual(failed["failure_count"], 1)
        self.assertEqual(failed["consecutive_failure_count"], 1)

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
        self.assertEqual(completed["supplier_identity_claim_count"], 0)
        self.assertEqual(completed["fx_rate_count"], 3)
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
        self.assertIn("خلاصه شکاف‌های داده", report_response.json()["content"])
        self.assertIn("توزیع قیمت‌های مشاهده‌شده", report_response.json()["content"])
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

        gaps_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/data-gaps"
        )
        self.assertEqual(gaps_response.status_code, 200)
        gaps = gaps_response.json()
        self.assertEqual(gaps["research_run_id"], run["id"])
        self.assertEqual(gaps["status"], "GAPS_REQUIRE_VERIFICATION")
        self.assertEqual(gaps["validation_disposition"], "NEEDS_VERIFICATION")
        self.assertEqual(gaps["confidence_score"], validation["confidence_score"])
        self.assertEqual(gaps["confidence_label"], validation["confidence_label"])
        self.assertEqual(gaps["issue_count"], len(validation["issues"]))
        self.assertEqual(gaps["error_count"], 0)
        self.assertEqual(gaps["warning_count"], len(validation["issues"]))
        self.assertEqual(gaps["declared_unknown_count"], len(bundle["unknowns"]))
        self.assertEqual(gaps["declared_unknowns"], sorted(bundle["unknowns"]))
        self.assertEqual(
            [item["code"] for item in gaps["issues"]],
            sorted(item["code"] for item in validation["issues"]),
        )
        self.assertNotIn("raw_value", json.dumps(gaps))

        executive_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/executive-summary"
        )
        self.assertEqual(executive_response.status_code, 200)
        executive = executive_response.json()
        self.assertEqual(executive["decision_status"], "VERIFICATION_REQUIRED")
        self.assertEqual(
            executive["recommendation_code"],
            "VERIFY_GAPS_BEFORE_PURCHASE",
        )
        self.assertEqual(
            executive["supplier_candidate_status"],
            "SINGLE_UNVERIFIED_CANDIDATE",
        )
        self.assertEqual(Decimal(executive["base_landed_cost_per_unit"]), Decimal("630"))
        self.assertEqual(executive["base_landed_cost_currency"], "IRR")
        self.assertEqual(
            executive["iran_market_benchmark_status"],
            "WITHHELD_NO_APPROVED_BENCHMARK",
        )
        self.assertIsNone(executive["iran_market_unit_price"])
        self.assertIsNone(executive["potential_gross_spread_per_unit"])
        self.assertIsNone(executive["potential_gross_spread_percent"])
        self.assertEqual(executive["data_gap_issue_count"], gaps["issue_count"])
        self.assertEqual(
            executive["declared_unknown_count"],
            gaps["declared_unknown_count"],
        )
        self.assertEqual(len(executive["leading_supplier_candidates"]), 1)
        candidate = executive["leading_supplier_candidates"][0]
        self.assertEqual(candidate["supplier_name"], "Demo Supplier — NOT REAL")
        self.assertEqual(candidate["due_diligence_status"], "UNVERIFIED")
        self.assertEqual(candidate["source_url"], "https://example.com/demo-supplier")
        self.assertNotIn("raw_value", json.dumps(executive))

        ledger_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/landed-cost-scenarios"
        )
        self.assertEqual(ledger_response.status_code, 200)
        ledger = ledger_response.json()
        self.assertEqual(ledger["research_run_id"], run["id"])
        self.assertEqual(
            [scenario["name"] for scenario in ledger["scenarios"]],
            ["OPTIMISTIC", "BASE", "CONSERVATIVE"],
        )
        base_scenario = ledger["scenarios"][1]
        self.assertEqual(base_scenario["total_amount"], "6300.00000000")
        self.assertEqual(base_scenario["per_unit_amount"], "630.00000000")
        self.assertEqual(
            [component["code"] for component in base_scenario["components"]],
            ["product_cost", "freight", "unexpected_cost"],
        )
        self.assertEqual(base_scenario["components"][0]["amount"], "5000.00000000")
        self.assertEqual(
            base_scenario["components"][0]["evidence_class"],
            "DERIVED_CALCULATION",
        )
        self.assertEqual(
            base_scenario["components"][0]["formula"],
            "converted unit price × purchase multiplier × quantity",
        )
        self.assertEqual(
            sum(Decimal(component["amount"]) for component in base_scenario["components"]),
            Decimal(base_scenario["total_amount"]),
        )
        self.assertEqual(ledger["scenario_sensitivity"]["range_percent_of_base"], "25.51")
        self.assertNotIn("raw_value", json.dumps(ledger))

        cost_coverage_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/cost-coverage"
        )
        self.assertEqual(cost_coverage_response.status_code, 200)
        cost_coverage = cost_coverage_response.json()
        self.assertEqual(cost_coverage["status"], "RECORDED_COST_COMPONENT_COVERAGE")
        self.assertEqual(
            [scenario["name"] for scenario in cost_coverage["scenarios"]],
            ["OPTIMISTIC", "BASE", "CONSERVATIVE"],
        )
        base_coverage = cost_coverage["scenarios"][1]
        self.assertEqual(
            base_coverage["recorded_component_codes"],
            ["freight", "product_cost", "unexpected_cost"],
        )
        self.assertEqual(base_coverage["recognized_reference_codes"], [
            "product_cost",
            "freight",
            "unexpected_cost",
        ])
        self.assertEqual(base_coverage["unclassified_component_codes"], [])
        self.assertEqual(base_coverage["assumption_count"], 2)
        self.assertEqual(base_coverage["derived_calculation_count"], 1)
        self.assertIn("insurance", base_coverage["unrecorded_reference_codes"])
        self.assertNotIn("raw_value", json.dumps(cost_coverage))

        fx_response = self.client.get(f"/api/v1/research-runs/{run['id']}/fx-rates")
        self.assertEqual(fx_response.status_code, 200)
        persisted_rates = fx_response.json()
        self.assertEqual(
            [item["scenario_name"] for item in persisted_rates],
            ["OPTIMISTIC", "BASE", "CONSERVATIVE"],
        )
        self.assertEqual({item["rate"] for item in persisted_rates}, {"100.000000000000"})
        self.assertTrue(all(item["rate_type"] == "SYNTHETIC_TEST" for item in persisted_rates))
        self.assertTrue(
            all(item["evidence_classification"] == "ASSUMPTION" for item in persisted_rates)
        )
        self.assertNotIn("raw_value", json.dumps(persisted_rates))

        assumptions_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/assumptions"
        )
        self.assertEqual(assumptions_response.status_code, 200)
        decision_notes = assumptions_response.json()
        self.assertEqual(decision_notes["research_run_id"], run["id"])
        self.assertEqual(decision_notes["assumptions"], bundle["assumptions"])
        self.assertEqual(decision_notes["unknowns"], bundle["unknowns"])

        evidence_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/evidence"
        )
        self.assertEqual(evidence_response.status_code, 200)
        evidence_catalog = evidence_response.json()
        self.assertEqual(len(evidence_catalog), 2)
        by_source = {item["source_name"]: item for item in evidence_catalog}
        supplier_evidence = by_source["Demo supplier — synthetic fixture"]
        self.assertEqual(
            supplier_evidence["usages"],
            [{"kind": "PRICE_OBSERVATION", "subject_id": "demo-price-1"}],
        )
        fx_evidence = by_source["Synthetic FX fixture"]
        self.assertEqual(len(fx_evidence["usages"]), 3)
        self.assertEqual({item["kind"] for item in fx_evidence["usages"]}, {"FX_RATE"})
        self.assertRegex(fx_evidence["fingerprint_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("raw_value", json.dumps(evidence_catalog))

        freshness_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/evidence-freshness"
        )
        self.assertEqual(freshness_response.status_code, 200)
        freshness = freshness_response.json()
        self.assertEqual(freshness["validation_policy_version"], validation["policy_version"])
        self.assertEqual(freshness["evidence_count"], completed["evidence_count"])
        self.assertEqual(
            freshness["current_count"]
            + freshness["within_clock_skew_count"]
            + freshness["stale_count"]
            + freshness["future_dated_count"],
            freshness["evidence_count"],
        )
        expected_freshness_status = (
            "FUTURE_DATED_EVIDENCE_RECORDED"
            if freshness["future_dated_count"]
            else (
                "STALE_EVIDENCE_RECORDED"
                if freshness["stale_count"]
                else "EVIDENCE_WITHIN_FRESHNESS_POLICY"
            )
        )
        self.assertEqual(freshness["status"], expected_freshness_status)
        self.assertEqual(freshness["max_age_seconds"], 30 * 24 * 60 * 60)
        self.assertEqual(freshness["future_clock_skew_seconds"], 5 * 60)
        self.assertEqual(
            {item["evidence_id"] for item in freshness["items"]},
            {item["id"] for item in evidence_catalog},
        )
        self.assertEqual(
            {item["fingerprint_sha256"] for item in freshness["items"]},
            {item["fingerprint_sha256"] for item in evidence_catalog},
        )
        freshness_by_source = {item["source_name"]: item for item in freshness["items"]}
        self.assertEqual(
            freshness_by_source["Demo supplier — synthetic fixture"]["usage_count"],
            1,
        )
        self.assertEqual(freshness_by_source["Synthetic FX fixture"]["usage_count"], 3)
        self.assertNotIn("raw_value", json.dumps(freshness))

        observations_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/price-observations"
        )
        self.assertEqual(observations_response.status_code, 200)
        observations = observations_response.json()
        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertEqual(observation["external_observation_id"], "demo-price-1")
        self.assertEqual(observation["original_amount"], "5.00000000")
        self.assertEqual(observation["original_currency"], "USD")
        self.assertEqual(observation["normalized_amount"], "500.00000000")
        self.assertEqual(observation["normalized_currency"], "IRR")
        self.assertEqual(observation["product_variant"], "DEMO")
        self.assertEqual(observation["product_attributes"], {"variant": "DEMO"})
        self.assertEqual(observation["market_layer"], "DEMO")
        self.assertEqual(
            observation["incoterm_named_place"],
            "Demo Factory Gate — NOT REAL",
        )
        self.assertEqual(observation["incoterm_version"], "2020")
        self.assertEqual(
            observation["payment_terms"],
            "Synthetic fixture only — 30% advance, 70% before shipment",
        )
        self.assertEqual(observation["payment_method"], "Synthetic bank transfer — NOT REAL")
        self.assertEqual(observation["quote_valid_until"], "2099-12-31T23:59:59Z")
        self.assertEqual(observation["lead_time_days"], 30)
        self.assertEqual(observation["product_match_classification"], "EXACT_VARIANT")
        self.assertEqual(observation["product_match_score"], 100)
        self.assertNotIn("raw_value", json.dumps(observations))

        quantity_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/quantity-analysis"
        )
        self.assertEqual(quantity_response.status_code, 200)
        quantity_analysis = quantity_response.json()
        self.assertEqual(quantity_analysis["status"], "OBSERVED_QUOTES_ONLY")
        self.assertEqual(quantity_analysis["requested_quantity"], 10)
        self.assertEqual(len(quantity_analysis["series"]), 1)
        self.assertEqual(
            quantity_analysis["series"][0]["product_name"],
            bundle["product_name"],
        )
        self.assertEqual(quantity_analysis["series"][0]["product_variant"], "DEMO")
        self.assertEqual(quantity_analysis["series"][0]["points"][0]["quoted_quantity"], 10)
        self.assertIsNone(
            quantity_analysis["series"][0]["points"][0][
                "normalized_change_from_previous_percent"
            ]
        )
        self.assertIsNone(quantity_analysis["economic_order_range_min"])
        self.assertIsNone(quantity_analysis["economic_order_range_max"])

        distribution_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/price-distribution"
        )
        self.assertEqual(distribution_response.status_code, 200)
        distribution = distribution_response.json()
        self.assertEqual(distribution["status"], "OBSERVED_DISTRIBUTIONS")
        self.assertEqual(distribution["excluded_observation_ids"], [])
        self.assertEqual(len(distribution["groups"]), 1)
        distribution_group = distribution["groups"][0]
        self.assertEqual(distribution_group["product_name"], bundle["product_name"])
        self.assertEqual(distribution_group["product_variant"], "DEMO")
        self.assertEqual(distribution_group["market_layer"], "DEMO")
        self.assertEqual(distribution_group["comparison_group"], "DEVICE:IRR")
        self.assertEqual(distribution_group["quoted_quantity"], 10)
        self.assertEqual(distribution_group["normalized_currency"], "IRR")
        self.assertEqual(distribution_group["observation_ids"], ["demo-price-1"])
        self.assertEqual(distribution_group["observation_count"], 1)
        self.assertEqual(distribution_group["distinct_source_count"], 1)
        for field in ("minimum_amount", "median_amount", "maximum_amount"):
            self.assertEqual(Decimal(distribution_group[field]), Decimal("500"))
        self.assertEqual(Decimal(distribution_group["range_amount"]), Decimal("0"))
        self.assertNotIn("raw_value", json.dumps(distribution))

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
        self.assertEqual(rankings[0]["original_amount"], "5.00000000")
        self.assertEqual(rankings[0]["original_currency"], "USD")
        self.assertEqual(rankings[0]["quoted_quantity"], 10)
        self.assertEqual(rankings[0]["minimum_order_quantity"], 10)
        self.assertEqual(rankings[0]["incoterm"], "EXW")
        self.assertEqual(
            rankings[0]["incoterm_named_place"],
            "Demo Factory Gate — NOT REAL",
        )
        self.assertEqual(rankings[0]["incoterm_version"], "2020")
        self.assertEqual(rankings[0]["payment_terms"], observation["payment_terms"])
        self.assertEqual(rankings[0]["payment_method"], observation["payment_method"])
        self.assertEqual(rankings[0]["quote_valid_until"], observation["quote_valid_until"])
        self.assertEqual(rankings[0]["lead_time_days"], 30)
        self.assertEqual(rankings[0]["source_name"], "Demo supplier — synthetic fixture")
        self.assertEqual(rankings[0]["source_url"], "https://example.com/demo-supplier")
        self.assertEqual(rankings[0]["retrieved_at"], "2026-08-31T00:00:00Z")
        self.assertEqual(rankings[0]["evidence_classification"], "ASSUMPTION")
        self.assertEqual(rankings[0]["evidence_confidence"], "UNKNOWN")
        self.assertNotIn("raw_value", rankings[0])

        coverage_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-coverage"
        )
        self.assertEqual(coverage_response.status_code, 200)
        coverage = coverage_response.json()
        self.assertEqual(coverage["status"], "SUPPLIER_EVIDENCE_COVERAGE")
        self.assertEqual(coverage["unidentified_observation_ids"], [])
        self.assertEqual(len(coverage["suppliers"]), 1)
        supplier = coverage["suppliers"][0]
        self.assertEqual(supplier["supplier_name"], "Demo Supplier — NOT REAL")
        self.assertEqual(supplier["observation_ids"], ["demo-price-1"])
        self.assertEqual(supplier["source_urls"], ["https://example.com/demo-supplier"])
        self.assertEqual(supplier["offer_count"], 1)
        self.assertEqual(supplier["distinct_source_count"], 1)
        self.assertEqual(supplier["moq_observation_count"], 1)
        self.assertEqual(supplier["incoterm_observation_count"], 1)
        self.assertEqual(supplier["rankable_offer_count"], 1)
        self.assertEqual(supplier["due_diligence_status"], "UNVERIFIED")
        self.assertIn("supplier_reliability", supplier["unknown_factors"])
        self.assertNotIn("raw_value", json.dumps(coverage))

        identity_claims_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims"
        )
        self.assertEqual(identity_claims_response.status_code, 200)
        self.assertEqual(
            identity_claims_response.json()["status"],
            "NO_SUPPLIER_IDENTITY_CLAIMS",
        )
        self.assertEqual(identity_claims_response.json()["claim_count"], 0)

        incoterm_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/incoterm-coverage"
        )
        self.assertEqual(incoterm_response.status_code, 200)
        incoterm_coverage = incoterm_response.json()
        self.assertEqual(
            incoterm_coverage["status"],
            "OBSERVED_INCOTERM_COVERAGE",
        )
        self.assertEqual(incoterm_coverage["reference_version"], "INCOTERMS_2020")
        self.assertEqual(incoterm_coverage["observed_recognized_codes"], ["EXW"])
        self.assertEqual(incoterm_coverage["unrecognized_declared_codes"], [])
        self.assertEqual(incoterm_coverage["missing_incoterm_observation_ids"], [])
        self.assertEqual(
            incoterm_coverage["comparison_status"],
            "WITHHELD_NO_INCOTERM_SCENARIOS",
        )
        self.assertEqual(incoterm_coverage["groups"][0]["code"], "EXW")
        self.assertTrue(incoterm_coverage["groups"][0]["recognized"])
        self.assertEqual(incoterm_coverage["groups"][0]["offer_count"], 1)
        self.assertEqual(incoterm_coverage["groups"][0]["named_supplier_count"], 1)
        self.assertEqual(
            incoterm_coverage["groups"][0]["named_places"],
            ["Demo Factory Gate — NOT REAL"],
        )
        self.assertEqual(incoterm_coverage["groups"][0]["declared_versions"], ["2020"])
        self.assertEqual(
            incoterm_coverage["groups"][0]["complete_terms_observation_count"],
            1,
        )
        self.assertEqual(incoterm_coverage["missing_named_place_observation_ids"], [])
        self.assertEqual(incoterm_coverage["missing_version_observation_ids"], [])
        self.assertNotIn("raw_value", json.dumps(incoterm_coverage))

        offer_terms_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/offer-terms-coverage"
        )
        self.assertEqual(offer_terms_response.status_code, 200)
        offer_terms = offer_terms_response.json()
        self.assertEqual(offer_terms["status"], "RECORDED_CORE_TERMS_PRESENT")
        self.assertEqual(len(offer_terms["offers"]), 1)
        offer_terms_item = offer_terms["offers"][0]
        self.assertEqual(offer_terms_item["observation_id"], "demo-price-1")
        self.assertEqual(
            offer_terms_item["declared_fields"],
            offer_terms["recorded_core_term_fields"],
        )
        self.assertEqual(offer_terms_item["missing_recorded_fields"], [])
        self.assertEqual(offer_terms_item["declared_recorded_field_count"], 10)
        self.assertTrue(offer_terms_item["rankable"])
        self.assertNotIn("payment_terms", offer_terms_item["ranking_unknown_factors"])
        self.assertNotIn("quote_valid_until", offer_terms["uncaptured_commercial_term_fields"])
        self.assertIn("supplier_capacity", offer_terms["uncaptured_commercial_term_fields"])
        self.assertNotIn("raw_value", json.dumps(offer_terms))

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
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(SupplierIdentityClaimRecord)),
                0,
            )
            self.assertEqual(connection.scalar(select(func.count()).select_from(FXRateRecord)), 3)
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

    def test_supplier_identity_claim_is_persisted_as_unreviewed_offer_scoped_evidence(
        self,
    ) -> None:
        raw_evidence = "SENSITIVE-SYNTHETIC-IDENTITY-EVIDENCE-998877"
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        bundle["supplier_identity_claims"] = [
            {
                "claim_id": "demo-identity-claim-1",
                "observation_id": "demo-price-1",
                "claimed_legal_name": "Demo Legal Supplier — NOT REAL",
                "jurisdiction": "Synthetic Fixture Jurisdiction",
                "registration_number": "SYNTHETIC-REG-001",
                "evidence": {
                    "classification": "FACT",
                    "source_name": "Synthetic registry — NOT REAL",
                    "source_url": "https://example.com/synthetic-registry",
                    "retrieved_at": "2026-09-01T00:00:00Z",
                    "raw_value": raw_evidence,
                    "confidence": "HIGH",
                    "transformation": "synthetic identity contract fixture",
                },
            }
        ]
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

        completed_response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "identity-claim-bundle"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        claims_response = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims"
        )
        hidden = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims",
            headers={"X-API-Key": self.other_api_key},
        )

        self.assertEqual(completed_response.status_code, 200)
        completed = completed_response.json()
        self.assertEqual(completed["supplier_identity_claim_count"], 1)
        self.assertEqual(completed["evidence_count"], 3)
        self.assertEqual(claims_response.status_code, 200)
        claims = claims_response.json()
        self.assertEqual(claims["research_run_id"], run["id"])
        self.assertEqual(claims["status"], "UNREVIEWED_IDENTITY_CLAIMS")
        self.assertEqual(claims["claim_count"], 1)
        claim = claims["claims"][0]
        self.assertEqual(claim["claim_id"], "demo-identity-claim-1")
        self.assertEqual(claim["observation_id"], "demo-price-1")
        self.assertEqual(claim["quoted_supplier_name"], "Demo Supplier — NOT REAL")
        self.assertEqual(claim["claimed_legal_name"], "Demo Legal Supplier — NOT REAL")
        self.assertEqual(claim["review_status"], "UNREVIEWED")
        self.assertEqual(claim["review_version"], 0)
        self.assertIsNone(claim["latest_reviewed_at"])
        self.assertEqual(claim["evidence_classification"], "FACT")
        self.assertEqual(claim["evidence_confidence"], "HIGH")
        self.assertNotIn("raw_value", json.dumps(claims))
        self.assertNotIn(raw_evidence, json.dumps(claims))
        self.assertEqual(hidden.status_code, 404)

        evidence_catalog = self.client.get(
            f"/api/v1/research-runs/{run['id']}/evidence"
        ).json()
        registry_evidence = next(
            item
            for item in evidence_catalog
            if item["source_name"] == "Synthetic registry — NOT REAL"
        )
        self.assertEqual(
            registry_evidence["usages"],
            [{"kind": "SUPPLIER_IDENTITY_CLAIM", "subject_id": "demo-identity-claim-1"}],
        )
        self.assertNotIn(raw_evidence, json.dumps(evidence_catalog))

        report_before_review = self.client.get(
            f"/api/v1/research-runs/{run['id']}/report"
        ).json()
        review_path = (
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims/"
            "demo-identity-claim-1/reviews"
        )
        hidden_review_read = self.client.get(
            review_path,
            headers={"X-API-Key": self.other_api_key},
        )
        hidden_review_write = self.client.post(
            review_path,
            headers={"X-API-Key": self.other_api_key},
            json={
                "decision": "EVIDENCE_SUPPORTED",
                "rationale": "Cross-tenant review must be rejected",
                "expected_version": 0,
            },
        )
        invalid_decision = self.client.post(
            review_path,
            json={
                "decision": "VERIFIED",
                "rationale": "Verification is not an allowed review decision",
                "expected_version": 0,
            },
        )
        invalid_claim_path = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims/"
            "invalid$claim/reviews"
        )
        first_review = self.client.post(
            review_path,
            headers={"X-Correlation-ID": "8c78777c-f236-41dc-b077-32914f00133c"},
            json={
                "decision": "EVIDENCE_SUPPORTED",
                "rationale": "Synthetic fixture evidence supports the submitted claim",
                "expected_version": 0,
            },
        )
        stale_review = self.client.post(
            review_path,
            json={
                "decision": "EVIDENCE_CONTRADICTED",
                "rationale": "A stale writer must not overwrite the append-only ledger",
                "expected_version": 0,
            },
        )
        second_review = self.client.post(
            review_path,
            json={
                "decision": "INCONCLUSIVE",
                "rationale": "The evidence requires another independent source",
                "expected_version": 1,
            },
        )
        review_history = self.client.get(review_path)
        reviewed_claims = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims"
        ).json()

        self.assertEqual(hidden_review_read.status_code, 404)
        self.assertEqual(hidden_review_write.status_code, 404)
        self.assertEqual(invalid_decision.status_code, 422)
        self.assertEqual(invalid_claim_path.status_code, 422)
        self.assertEqual(first_review.status_code, 201)
        first_review_body = first_review.json()
        self.assertEqual(first_review_body["previous_status"], "UNREVIEWED")
        self.assertEqual(first_review_body["resulting_status"], "EVIDENCE_SUPPORTED")
        self.assertEqual(first_review_body["previous_version"], 0)
        self.assertEqual(first_review_body["resulting_version"], 1)
        self.assertTrue(first_review_body["reviewer_actor_id"].startswith("api-key:"))
        self.assertEqual(stale_review.status_code, 409)
        self.assertEqual(stale_review.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(second_review.status_code, 201)
        self.assertEqual(second_review.json()["previous_status"], "EVIDENCE_SUPPORTED")
        self.assertEqual(second_review.json()["resulting_status"], "INCONCLUSIVE")
        self.assertEqual(second_review.json()["resulting_version"], 2)
        self.assertEqual(review_history.status_code, 200)
        self.assertEqual(
            [item["resulting_version"] for item in review_history.json()],
            [1, 2],
        )
        self.assertEqual(reviewed_claims["status"], "REVIEWED_IDENTITY_CLAIMS")
        reviewed_claim = reviewed_claims["claims"][0]
        self.assertEqual(reviewed_claim["review_status"], "INCONCLUSIVE")
        self.assertEqual(reviewed_claim["review_version"], 2)
        self.assertIsNotNone(reviewed_claim["latest_reviewed_at"])

        ranking = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-offer-rankings"
        ).json()[0]
        coverage = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-coverage"
        ).json()["suppliers"][0]
        self.assertIn("supplier_reliability", ranking["unknown_factors"])
        self.assertEqual(coverage["due_diligence_status"], "UNVERIFIED")

        report = self.client.get(f"/api/v1/research-runs/{run['id']}/report").json()
        self.assertEqual(report["content_sha256"], report_before_review["content_sha256"])
        self.assertIn("Demo Legal Supplier — NOT REAL", report["content"])
        self.assertIn("`UNREVIEWED`", report["content"])
        self.assertNotIn("another independent source", report["content"])
        self.assertNotIn(raw_evidence, report["content"])

        with self.engine.connect() as connection:
            persisted_count = connection.scalar(
                select(func.count())
                .select_from(SupplierIdentityClaimRecord)
                .where(SupplierIdentityClaimRecord.research_run_id == run["id"])
            )
            review_count = connection.scalar(
                select(func.count())
                .select_from(SupplierIdentityClaimReviewRecord)
                .where(SupplierIdentityClaimReviewRecord.research_run_id == run["id"])
            )
            review_audits = connection.execute(
                select(
                    AuditEventRecord.correlation_id,
                    AuditEventRecord.payload,
                )
                .where(AuditEventRecord.action == "IDENTITY_CLAIM_REVIEW_RECORDED")
                .order_by(AuditEventRecord.occurred_at)
            ).all()
        self.assertEqual(persisted_count, 1)
        self.assertEqual(review_count, 2)
        self.assertEqual(len(review_audits), 2)
        self.assertEqual(
            review_audits[0].correlation_id,
            "8c78777c-f236-41dc-b077-32914f00133c",
        )
        self.assertEqual(
            [item.payload["resulting_version"] for item in review_audits],
            [1, 2],
        )
        self.assertNotIn("rationale", json.dumps([item.payload for item in review_audits]))
        self.assertNotIn(raw_evidence, json.dumps([item.payload for item in review_audits]))

    def test_scenario_specific_fx_is_persisted_with_exact_lineage(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        scenario_rates = {
            "OPTIMISTIC": "90",
            "BASE": "100",
            "CONSERVATIVE": "110",
        }
        for scenario in bundle["scenarios"]:
            scenario_rate = deepcopy(bundle["fx_rates"][0])
            scenario_rate["rate"] = scenario_rates[scenario["name"]]
            scenario_rate["rate_type"] = "SYNTHETIC_SCENARIO"
            scenario_rate["evidence"]["raw_value"] = (
                f"Synthetic {scenario['name']} FX assumption: {scenario_rate['rate']}"
            )
            scenario["fx_rates"] = [scenario_rate]

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
            headers={"Idempotency-Key": "scenario-specific-fx"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.json()["fx_rate_count"], 3)

        persisted_rates = self.client.get(
            f"/api/v1/research-runs/{run['id']}/fx-rates"
        ).json()
        self.assertEqual(
            {item["scenario_name"]: item["rate"] for item in persisted_rates},
            {
                "OPTIMISTIC": "90.000000000000",
                "BASE": "100.000000000000",
                "CONSERVATIVE": "110.000000000000",
            },
        )
        ledger = self.client.get(
            f"/api/v1/research-runs/{run['id']}/landed-cost-scenarios"
        ).json()
        self.assertEqual(
            {item["name"]: item["per_unit_amount"] for item in ledger["scenarios"]},
            {
                "OPTIMISTIC": "527.85000000",
                "BASE": "630.00000000",
                "CONSERVATIVE": "797.50000000",
            },
        )
        self.assertEqual(
            ledger["scenario_sensitivity"]["range_percent_of_base"],
            "42.80",
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

    def test_request_validation_does_not_reflect_invalid_input(self) -> None:
        secret = "COMMERCIAL-SECRET-PRICE-998877"
        response = self.client.post(
            "/api/v1/opportunities",
            json={
                "product_name": "Pump",
                "quantity": secret,
                "target_market": "Tehran",
            },
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["code"], "REQUEST_VALIDATION_FAILED")
        self.assertEqual(body["message"], "request validation failed")
        self.assertEqual(
            body["details"],
            [
                {
                    "location": ["body", "quantity"],
                    "code": "int_parsing",
                    "message": "invalid value",
                }
            ],
        )
        self.assertNotIn(secret, response.text)
        self.assertNotIn("input", response.text)

    def test_non_public_value_error_does_not_reflect_domain_identifier(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        secret = "COMMERCIAL-SECRET-COST-CODE-998877"
        bundle["scenarios"][0]["costs"][0]["code"] = secret
        bundle["scenarios"][0]["costs"][0]["money"]["amount"] = "-1"
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
        self.client.post(
            f"/api/v1/research-runs/{run['id']}/transitions",
            json={"target_status": "RUNNING", "expected_version": 1},
        )

        response = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "non-reflective-domain-error"},
            json={"expected_version": 2, "bundle": bundle},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INVALID_INPUT")
        self.assertEqual(response.json()["message"], "request input is invalid")
        self.assertNotIn(secret, response.text)

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
