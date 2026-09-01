import hashlib
import json
import os
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.exc import IntegrityError

from trade_agent.api.app import create_app
from trade_agent.config import Settings
from trade_agent.infrastructure.database import (
    AuditEventRecord,
    IdempotencyRecord,
    LandedCostScenarioRecord,
    OpportunityRecord,
    ResearchReviewRecord,
    ResearchRunRecord,
    SupplierIdentityClaimRecord,
    SupplierIdentityClaimReviewRecord,
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
            api_key_roles={
                hashlib.sha256(cls.api_key.encode()).hexdigest(): [
                    "RESEARCH_REVIEWER",
                    "SUPPLIER_IDENTITY_REVIEWER",
                ],
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
        self.assertEqual(readiness.json()["schema_revision"], "20260901_0015")

        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        bundle["supplier_identity_claims"] = [
            {
                "claim_id": "postgres-identity-claim-1",
                "observation_id": "demo-price-1",
                "claimed_legal_name": "PostgreSQL Legal Supplier Fixture",
                "jurisdiction": "PostgreSQL Fixture Jurisdiction",
                "registration_number": "POSTGRES-FIXTURE-001",
                "evidence": {
                    "classification": "FACT",
                    "source_name": "PostgreSQL synthetic registry fixture",
                    "source_url": "https://example.com/postgres-synthetic-registry",
                    "retrieved_at": "2026-09-01T00:00:00Z",
                    "raw_value": "POSTGRES-SENSITIVE-SYNTHETIC-IDENTITY-BODY",
                    "confidence": "HIGH",
                    "transformation": "PostgreSQL identity contract fixture",
                },
            }
        ]
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
        self.assertEqual(completed["supplier_identity_claim_count"], 1)

        replay = self.client.post(
            f"/api/v1/research-runs/{run['id']}/evidence-bundle",
            headers={"Idempotency-Key": "postgres-ci-completion"},
            json={"expected_version": running["version"], "bundle": bundle},
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["idempotency_replayed"])

        research_review_queue = self.client.get("/api/v1/research-review-queue")
        self.assertEqual(research_review_queue.status_code, 200)
        self.assertEqual(len(research_review_queue.json()["items"]), 1)
        queued_research = research_review_queue.json()["items"][0]
        self.assertEqual(queued_research["research_run_id"], run["id"])
        self.assertEqual(queued_research["research_status"], "NEEDS_VERIFICATION")
        self.assertEqual(queued_research["expected_version"], completed["version"])
        self.assertEqual(queued_research["report_sha256"], completed["report_sha256"])
        self.assertGreater(queued_research["data_gap_warning_count"], 0)
        self.assertNotIn(
            "POSTGRES-SENSITIVE-SYNTHETIC-IDENTITY-BODY",
            json.dumps(research_review_queue.json()),
        )

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
        self.assertEqual(
            self.client.get("/api/v1/research-review-queue").json()["items"],
            [],
        )

        successor_path = f"/api/v1/research-runs/{run['id']}/successors"
        successor_payload = {
            "expected_version": review.json()["resulting_version"],
            "reason": "PostgreSQL fixture requires an explicit recalculation run",
        }
        successor = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "postgres-ci-successor"},
            json=successor_payload,
        )
        successor_replay = self.client.post(
            successor_path,
            headers={"Idempotency-Key": "postgres-ci-successor"},
            json=successor_payload,
        )
        self.assertEqual(successor.status_code, 201)
        self.assertEqual(successor.json()["supersedes_research_run_id"], run["id"])
        self.assertFalse(successor.json()["idempotency_replayed"])
        self.assertEqual(successor_replay.status_code, 201)
        self.assertEqual(successor_replay.json()["id"], successor.json()["id"])
        self.assertTrue(successor_replay.json()["idempotency_replayed"])
        self.assertEqual(
            self.client.get(
                f"/api/v1/research-runs/{successor.json()['id']}/report"
            ).status_code,
            404,
        )

        latest_decision = self.client.get(
            f"/api/v1/opportunities/{opportunity['id']}/latest-decision"
        )
        self.assertEqual(latest_decision.status_code, 200)
        self.assertEqual(latest_decision.json()["research_run"]["id"], run["id"])
        self.assertIsNone(
            latest_decision.json()["research_run"]["supersedes_research_run_id"]
        )
        self.assertEqual(
            latest_decision.json()["report"]["content_sha256"],
            completed["report_sha256"],
        )
        self.assertEqual(len(latest_decision.json()["scenarios"]), 3)
        decision_executive = latest_decision.json()["executive_summary"]
        self.assertEqual(decision_executive["decision_status"], "VERIFICATION_REQUIRED")
        self.assertEqual(
            decision_executive["supplier_candidate_status"],
            "SINGLE_UNVERIFIED_CANDIDATE",
        )
        self.assertEqual(
            Decimal(decision_executive["base_landed_cost_per_unit"]),
            Decimal("630"),
        )
        self.assertIsNone(decision_executive["iran_market_unit_price"])

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
        cost_coverage = self.client.get(
            f"/api/v1/research-runs/{run['id']}/cost-coverage"
        )
        self.assertEqual(cost_coverage.status_code, 200)
        self.assertEqual(
            cost_coverage.json()["status"],
            "RECORDED_COST_COMPONENT_COVERAGE",
        )
        self.assertEqual(
            cost_coverage.json()["scenarios"][1]["recorded_component_count"],
            len(base_scenario["components"]),
        )
        self.assertIn(
            "tariff_duty",
            cost_coverage.json()["scenarios"][1]["unrecorded_reference_codes"],
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
        executive_summary = self.client.get(
            f"/api/v1/research-runs/{run['id']}/executive-summary"
        )
        self.assertEqual(executive_summary.status_code, 200)
        self.assertEqual(
            executive_summary.json()["decision_status"],
            "VERIFICATION_REQUIRED",
        )
        self.assertEqual(
            executive_summary.json()["iran_market_benchmark_status"],
            "WITHHELD_NO_APPROVED_BENCHMARK",
        )
        self.assertIsNone(executive_summary.json()["potential_gross_spread_per_unit"])
        self.assertEqual(
            Decimal(executive_summary.json()["base_landed_cost_per_unit"]),
            Decimal("630"),
        )
        self.assertNotIn("raw_value", json.dumps(executive_summary.json()))
        evidence_catalog = self.client.get(
            f"/api/v1/research-runs/{run['id']}/evidence"
        )
        self.assertEqual(evidence_catalog.status_code, 200)
        self.assertEqual(len(evidence_catalog.json()), completed["evidence_count"])
        self.assertNotIn("raw_value", json.dumps(evidence_catalog.json()))
        evidence_freshness = self.client.get(
            f"/api/v1/research-runs/{run['id']}/evidence-freshness"
        )
        self.assertEqual(evidence_freshness.status_code, 200)
        self.assertEqual(
            evidence_freshness.json()["evidence_count"],
            completed["evidence_count"],
        )
        self.assertEqual(
            sum(
                evidence_freshness.json()[field]
                for field in (
                    "current_count",
                    "within_clock_skew_count",
                    "stale_count",
                    "future_dated_count",
                )
            ),
            completed["evidence_count"],
        )
        self.assertEqual(
            sum(item["usage_count"] for item in evidence_freshness.json()["items"]),
            completed["price_observation_count"]
            + completed["fx_rate_count"]
            + completed["supplier_identity_claim_count"],
        )
        self.assertNotIn("raw_value", json.dumps(evidence_freshness.json()))
        price_observations = self.client.get(
            f"/api/v1/research-runs/{run['id']}/price-observations"
        )
        self.assertEqual(price_observations.status_code, 200)
        self.assertEqual(len(price_observations.json()), completed["price_observation_count"])
        self.assertEqual(price_observations.json()[0]["normalized_currency"], "IRR")
        self.assertEqual(
            price_observations.json()[0]["incoterm_named_place"],
            "Demo Factory Gate — NOT REAL",
        )
        self.assertEqual(price_observations.json()[0]["incoterm_version"], "2020")
        self.assertEqual(
            price_observations.json()[0]["payment_terms"],
            "Synthetic fixture only — 30% advance, 70% before shipment",
        )
        self.assertEqual(
            price_observations.json()[0]["quote_valid_until"],
            "2099-12-31T23:59:59Z",
        )
        self.assertEqual(price_observations.json()[0]["lead_time_days"], 30)
        incoterm_coverage = self.client.get(
            f"/api/v1/research-runs/{run['id']}/incoterm-coverage"
        )
        self.assertEqual(incoterm_coverage.status_code, 200)
        self.assertEqual(
            incoterm_coverage.json()["status"],
            "OBSERVED_INCOTERM_COVERAGE",
        )
        self.assertEqual(
            incoterm_coverage.json()["observed_recognized_codes"],
            ["EXW"],
        )
        self.assertEqual(
            incoterm_coverage.json()["comparison_status"],
            "WITHHELD_NO_INCOTERM_SCENARIOS",
        )
        self.assertEqual(
            incoterm_coverage.json()["groups"][0]["complete_terms_observation_count"],
            1,
        )
        self.assertNotIn("raw_value", json.dumps(incoterm_coverage.json()))
        offer_terms = self.client.get(
            f"/api/v1/research-runs/{run['id']}/offer-terms-coverage"
        )
        self.assertEqual(offer_terms.status_code, 200)
        self.assertEqual(
            offer_terms.json()["status"],
            "RECORDED_CORE_TERMS_PRESENT",
        )
        self.assertEqual(
            offer_terms.json()["offers"][0]["declared_recorded_field_count"],
            len(offer_terms.json()["recorded_core_term_fields"]),
        )
        self.assertNotIn(
            "payment_terms",
            offer_terms.json()["uncaptured_commercial_term_fields"],
        )
        self.assertIn(
            "supplier_capacity",
            offer_terms.json()["uncaptured_commercial_term_fields"],
        )
        self.assertNotIn("raw_value", json.dumps(offer_terms.json()))
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
        identity_claims = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims"
        )
        self.assertEqual(identity_claims.status_code, 200)
        self.assertEqual(identity_claims.json()["status"], "UNREVIEWED_IDENTITY_CLAIMS")
        self.assertEqual(identity_claims.json()["claim_count"], 1)
        self.assertEqual(
            identity_claims.json()["claims"][0]["registration_number"],
            "POSTGRES-FIXTURE-001",
        )
        self.assertEqual(identity_claims.json()["claims"][0]["review_status"], "UNREVIEWED")
        self.assertEqual(identity_claims.json()["claims"][0]["review_version"], 0)
        self.assertNotIn("raw_value", json.dumps(identity_claims.json()))
        identity_review_queue = self.client.get(
            "/api/v1/supplier-identity-review-queue"
        )
        self.assertEqual(identity_review_queue.status_code, 200)
        self.assertEqual(len(identity_review_queue.json()["items"]), 1)
        self.assertEqual(
            identity_review_queue.json()["items"][0]["claim_id"],
            "postgres-identity-claim-1",
        )
        self.assertEqual(
            identity_review_queue.json()["items"][0]["review_status"],
            "UNREVIEWED",
        )
        self.assertNotIn(
            "POSTGRES-SENSITIVE-SYNTHETIC-IDENTITY-BODY",
            json.dumps(identity_review_queue.json()),
        )

        identity_review_path = (
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims/"
            "postgres-identity-claim-1/reviews"
        )
        identity_review = self.client.post(
            identity_review_path,
            json={
                "decision": "EVIDENCE_SUPPORTED",
                "rationale": "PostgreSQL fixture evidence supports this scoped claim",
                "expected_version": 0,
            },
        )
        stale_identity_review = self.client.post(
            identity_review_path,
            json={
                "decision": "INCONCLUSIVE",
                "rationale": "The stale PostgreSQL writer must be rejected",
                "expected_version": 0,
            },
        )
        identity_review_history = self.client.get(identity_review_path)
        reviewed_identity_claims = self.client.get(
            f"/api/v1/research-runs/{run['id']}/supplier-identity-claims"
        )
        resolved_identity_review_queue = self.client.get(
            "/api/v1/supplier-identity-review-queue"
        )
        report_after_identity_review = self.client.get(
            f"/api/v1/research-runs/{run['id']}/report"
        )

        self.assertEqual(identity_review.status_code, 201)
        self.assertEqual(identity_review.json()["previous_status"], "UNREVIEWED")
        self.assertEqual(identity_review.json()["resulting_status"], "EVIDENCE_SUPPORTED")
        self.assertEqual(identity_review.json()["resulting_version"], 1)
        self.assertEqual(stale_identity_review.status_code, 409)
        self.assertEqual(stale_identity_review.json()["code"], "VERSION_CONFLICT")
        self.assertEqual(identity_review_history.status_code, 200)
        self.assertEqual(len(identity_review_history.json()), 1)
        self.assertEqual(reviewed_identity_claims.status_code, 200)
        self.assertEqual(
            reviewed_identity_claims.json()["status"],
            "REVIEWED_IDENTITY_CLAIMS",
        )
        self.assertEqual(
            reviewed_identity_claims.json()["claims"][0]["review_status"],
            "EVIDENCE_SUPPORTED",
        )
        self.assertEqual(reviewed_identity_claims.json()["claims"][0]["review_version"], 1)
        self.assertEqual(resolved_identity_review_queue.status_code, 200)
        self.assertEqual(resolved_identity_review_queue.json()["items"], [])
        self.assertEqual(report_after_identity_review.status_code, 200)
        self.assertEqual(
            report_after_identity_review.json()["content_sha256"],
            completed["report_sha256"],
        )
        self.assertIn("`UNREVIEWED`", report_after_identity_review.json()["content"])

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

        historical_audit_id = str(uuid4())
        historical_audit_payload = {
            "decision": "APPROVE",
            "rationale": "POSTGRES-SENSITIVE-HISTORICAL-RATIONALE",
            "from": "NEEDS_VERIFICATION",
            "to": "COMPLETED",
            "version": 99,
            "unexpected_private_note": "POSTGRES-SENSITIVE-UNEXPECTED-FIELD",
        }
        with self.engine.begin() as connection:
            connection.execute(
                insert(AuditEventRecord).values(
                    id=historical_audit_id,
                    tenant_id="postgres-ci",
                    actor_id="api-key:historical",
                    correlation_id=str(uuid4()),
                    aggregate_type="ResearchRun",
                    aggregate_id=str(uuid4()),
                    action="REVIEW_RECORDED",
                    payload=historical_audit_payload,
                    occurred_at=datetime.now(UTC),
                )
            )

        audit_ids: list[str] = []
        audit_payloads: dict[str, dict[str, object]] = {}
        audit_cursor: str | None = None
        while True:
            params: dict[str, int | str] = {"limit": 3}
            if audit_cursor is not None:
                params["after"] = audit_cursor
            audit_page_response = self.client.get("/api/v1/audit-events", params=params)
            self.assertEqual(audit_page_response.status_code, 200)
            audit_page = audit_page_response.json()
            audit_ids.extend(event["id"] for event in audit_page["items"])
            audit_payloads.update(
                {event["id"]: event["payload"] for event in audit_page["items"]}
            )
            audit_cursor = audit_page["next_cursor"]
            if audit_cursor is None:
                break
        self.assertEqual(len(audit_ids), len(set(audit_ids)))
        self.assertEqual(
            audit_payloads[historical_audit_id],
            {
                "decision": "APPROVE",
                "from": "NEEDS_VERIFICATION",
                "to": "COMPLETED",
                "version": 99,
            },
        )

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
            stored_historical_audit_payload = connection.scalar(
                select(AuditEventRecord.payload).where(
                    AuditEventRecord.id == historical_audit_id
                )
            )
            research_review_audit_payload = connection.scalar(
                select(AuditEventRecord.payload).where(
                    AuditEventRecord.aggregate_id == run["id"],
                    AuditEventRecord.action == "REVIEW_RECORDED",
                )
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
            identity_claim_count = connection.scalar(
                select(func.count())
                .select_from(SupplierIdentityClaimRecord)
                .where(SupplierIdentityClaimRecord.research_run_id == run["id"])
            )
            identity_claim_database_id = connection.scalar(
                select(SupplierIdentityClaimRecord.id).where(
                    SupplierIdentityClaimRecord.research_run_id == run["id"]
                )
            )
            identity_claim_review_count = connection.scalar(
                select(func.count())
                .select_from(SupplierIdentityClaimReviewRecord)
                .where(SupplierIdentityClaimReviewRecord.research_run_id == run["id"])
            )
            successor_lineage = connection.execute(
                select(
                    ResearchRunRecord.supersedes_research_run_id,
                    ResearchRunRecord.recalculation_reason,
                ).where(ResearchRunRecord.id == successor.json()["id"])
            ).one()

        self.assertEqual(tenant_id, "postgres-ci")
        self.assertIsInstance(total, Decimal)
        self.assertIsInstance(audit_payload, dict)
        self.assertEqual(len(audit_ids), audit_count)
        self.assertEqual(stored_historical_audit_payload, historical_audit_payload)
        self.assertEqual(idempotency_count, 2)
        self.assertEqual(review_count, 1)
        self.assertEqual(
            research_review_audit_payload,
            {
                "decision": "APPROVE",
                "from": "NEEDS_VERIFICATION",
                "to": "COMPLETED",
                "version": review.json()["resulting_version"],
            },
        )
        self.assertNotIn("rationale", research_review_audit_payload)
        self.assertEqual(identity_claim_count, 1)
        self.assertEqual(identity_claim_review_count, 1)
        self.assertIsNotNone(identity_claim_database_id)
        self.assertEqual(successor_lineage.supersedes_research_run_id, run["id"])
        self.assertEqual(
            successor_lineage.recalculation_reason,
            successor_payload["reason"],
        )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(SupplierIdentityClaimReviewRecord).values(
                    id=str(uuid4()),
                    tenant_id="postgres-ci",
                    research_run_id=run["id"],
                    supplier_identity_claim_id=identity_claim_database_id,
                    reviewer_actor_id="postgres-native-constraint-test",
                    decision="VERIFIED",
                    rationale="This forbidden state must fail at the database boundary",
                    previous_status="UNREVIEWED",
                    resulting_status="VERIFIED",
                    previous_version=0,
                    resulting_version=1,
                    created_at=func.now(),
                )
            )

        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(ResearchRunRecord).values(
                    id=str(uuid4()),
                    tenant_id="postgres-ci",
                    opportunity_id=opportunity["id"],
                    supersedes_research_run_id=None,
                    recalculation_reason="Orphaned recalculation reason",
                    status="CREATED",
                    version=1,
                    created_at=func.now(),
                    updated_at=func.now(),
                )
            )

        self_superseding_id = str(uuid4())
        with self.assertRaises(IntegrityError), self.engine.begin() as connection:
            connection.execute(
                insert(ResearchRunRecord).values(
                    id=self_superseding_id,
                    tenant_id="postgres-ci",
                    opportunity_id=opportunity["id"],
                    supersedes_research_run_id=self_superseding_id,
                    recalculation_reason="Invalid self-reference",
                    status="CREATED",
                    version=1,
                    created_at=func.now(),
                    updated_at=func.now(),
                )
            )


if __name__ == "__main__":
    unittest.main()
