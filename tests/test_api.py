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
        self.assertNotIn("tenant_id", decision.text)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json()["code"], "NOT_FOUND")

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
                "product-matches",
                "supplier-offer-rankings",
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
        unavailable = self.client.get("/api/v1/reference-rates/ecb/USD")
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
            disabled_rate = disabled_client.get("/api/v1/reference-rates/ecb/USD")

        self.assertFalse(disabled_catalog.json()[0]["enabled"])
        self.assertEqual(disabled_rate.status_code, 502)
        self.assertEqual(disabled_rate.json()["code"], "UPSTREAM_UNAVAILABLE")
        self.assertEqual(disabled_rates.calls, 0)

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
        self.assertEqual(rankings[0]["original_amount"], "5.00000000")
        self.assertEqual(rankings[0]["original_currency"], "USD")
        self.assertEqual(rankings[0]["quoted_quantity"], 10)
        self.assertEqual(rankings[0]["minimum_order_quantity"], 10)
        self.assertEqual(rankings[0]["incoterm"], "EXW")
        self.assertEqual(rankings[0]["source_name"], "Demo supplier — synthetic fixture")
        self.assertEqual(rankings[0]["source_url"], "https://example.com/demo-supplier")
        self.assertEqual(rankings[0]["retrieved_at"], "2026-08-31T00:00:00Z")
        self.assertEqual(rankings[0]["evidence_classification"], "ASSUMPTION")
        self.assertEqual(rankings[0]["evidence_confidence"], "UNKNOWN")
        self.assertNotIn("raw_value", rankings[0])

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
