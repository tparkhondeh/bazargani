import json
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from trade_agent.application.research import execute_research_case
from trade_agent.domain.errors import PublicInputError
from trade_agent.providers.evidence_bundle import load_evidence_bundle, parse_evidence_bundle
from trade_agent.reporting.markdown import render_markdown


class EvidenceBundleTests(unittest.TestCase):
    @staticmethod
    def _identity_claim() -> dict[str, object]:
        return {
            "claim_id": "synthetic-identity-claim-1",
            "observation_id": "demo-price-1",
            "claimed_legal_name": '<img src=x onerror="not-real"> Fixture Legal Name',
            "jurisdiction": "Synthetic Fixture Jurisdiction",
            "registration_number": "SYNTHETIC-REG-001`",
            "evidence": {
                "classification": "FACT",
                "source_name": "Synthetic registry — NOT REAL",
                "source_url": "https://example.com/synthetic-registry",
                "retrieved_at": "2026-09-01T00:00:00Z",
                "raw_value": "SENSITIVE-SYNTHETIC-REGISTRY-BODY-998877",
                "confidence": "HIGH",
                "transformation": "synthetic identity fixture only",
            },
        }

    def test_demo_bundle_runs_end_to_end(self) -> None:
        case = load_evidence_bundle(Path("examples/demo_case.json"))
        result = execute_research_case(case)
        report = render_markdown(result)
        self.assertEqual(len(result.scenarios), 3)
        self.assertIn("DEMO-NOT-MARKET-DATA", report)
        self.assertIn("مجهولات", report)
        self.assertIn("خلاصه شکاف‌های داده", report)
        self.assertIn("مجهول اعلام‌شده: 1", report)
        self.assertIn("خلاصه اجرایی تصمیم", report)
        self.assertIn("`WITHHELD_NO_APPROVED_BENCHMARK`", report)
        self.assertIn("تازگی شواهد", report)
        self.assertIn("زمان مبنای ارزیابی", report)
        self.assertIn("https://example.com/demo-supplier", report)
        self.assertIn("EXACT_VARIANT", report)
        self.assertIn("تطبیق محصول", report)
        self.assertIn("رتبه‌بندی پیشنهادهای تأمین‌کننده", report)
        self.assertIn("پوشش شواهد تأمین‌کننده", report)
        self.assertIn("راستی‌آزمایی `UNVERIFIED`", report)
        self.assertIn("پوشش شواهد Incoterm", report)
        self.assertIn("WITHHELD_NO_INCOTERM_SCENARIOS", report)
        self.assertIn("Demo Factory Gate — NOT REAL", report)
        self.assertIn("نسخه‌های اعلام‌شده: `2020`", report)
        self.assertIn("پوشش شروط ثبت‌شده پیشنهادها", report)
        self.assertIn("فیلدهای تجاری خارج از schema فعلی", report)
        self.assertIn(r"supplier\_reliability", report)
        self.assertIn("حساسیت سناریوها", report)
        self.assertIn("پوشش اجزای هزینه", report)
        self.assertIn("دسته‌های مرجع ثبت‌نشده", report)
        self.assertIn("25.51%", report)
        self.assertIn("نرخ‌های ارز سناریوها", report)
        self.assertEqual(report.count("1 `USD` = 100 `IRR`"), 3)
        self.assertIn("تحلیل تعداد", report)
        self.assertIn("بازه سفارش اقتصادی: محاسبه نشده", report)
        self.assertIn("توزیع قیمت‌های مشاهده‌شده", report)
        self.assertIn("کمینه 500.00", report)

    def test_duplicate_scenario_names_are_rejected_before_calculation(self) -> None:
        case = load_evidence_bundle(Path("examples/demo_case.json"))
        duplicate = replace(case, scenarios=(*case.scenarios, case.scenarios[1]))

        with self.assertRaisesRegex(ValueError, "scenario names must be unique"):
            execute_research_case(duplicate)

    def test_identity_claim_is_evidence_bound_unreviewed_and_does_not_change_ranking(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        baseline = execute_research_case(parse_evidence_bundle(bundle))
        bundle["supplier_identity_claims"] = [self._identity_claim()]

        result = execute_research_case(parse_evidence_bundle(bundle))
        report = render_markdown(result)
        claim = result.case.supplier_identity_claims[0]

        self.assertEqual(claim.claim_id, "synthetic-identity-claim-1")
        self.assertEqual(claim.observation_id, "demo-price-1")
        self.assertEqual(
            result.supplier_rankings[0].total_score,
            baseline.supplier_rankings[0].total_score,
        )
        self.assertIn(
            "SUPPLIER_IDENTITY_CLAIM_REQUIRES_REVIEW",
            {issue.code for issue in result.validation.issues},
        )
        self.assertIn("ادعاهای هویت حقوقی تأمین‌کننده", report)
        self.assertIn("`UNREVIEWED`", report)
        self.assertIn("&lt;img src=x onerror=\"not-real\"&gt;", report)
        self.assertNotIn("SENSITIVE-SYNTHETIC-REGISTRY-BODY-998877", report)

    def test_identity_claim_references_and_identifiers_fail_closed(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        unknown = self._identity_claim()
        unknown["observation_id"] = "missing-observation"
        bundle["supplier_identity_claims"] = [unknown]
        with self.assertRaisesRegex(ValueError, "unknown observations"):
            parse_evidence_bundle(bundle)

        duplicate_bundle = json.loads(
            Path("examples/demo_case.json").read_text(encoding="utf-8")
        )
        duplicate_bundle["supplier_identity_claims"] = [
            self._identity_claim(),
            deepcopy(self._identity_claim()),
        ]
        with self.assertRaisesRegex(ValueError, "claim_id values must be unique"):
            parse_evidence_bundle(duplicate_bundle)

    def test_identity_claim_requires_exact_bounded_public_fields(self) -> None:
        invalid_values = (
            ("claimed_legal_name", None, "must be a string"),
            ("jurisdiction", "   ", "cannot be empty"),
            ("registration_number", "x" * 101, "at most 100"),
        )
        for field, value, expected in invalid_values:
            with self.subTest(field=field):
                bundle = json.loads(
                    Path("examples/demo_case.json").read_text(encoding="utf-8")
                )
                claim = self._identity_claim()
                claim[field] = value
                bundle["supplier_identity_claims"] = [claim]
                with self.assertRaisesRegex(ValueError, expected):
                    parse_evidence_bundle(bundle)

        oversized = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        oversized["supplier_identity_claims"] = [self._identity_claim()] * 501
        with self.assertRaisesRegex(ValueError, "more than 500"):
            parse_evidence_bundle(oversized)

    def test_claim_for_deduplicated_observation_is_excluded_explicitly(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        duplicate = deepcopy(bundle["observations"][0])
        duplicate["observation_id"] = "demo-price-duplicate"
        bundle["observations"].append(duplicate)
        claim = self._identity_claim()
        claim["observation_id"] = "demo-price-duplicate"
        bundle["supplier_identity_claims"] = [claim]

        result = execute_research_case(parse_evidence_bundle(bundle))

        self.assertEqual(result.case.supplier_identity_claims, ())
        self.assertIn(
            "IDENTITY_CLAIM_FOR_EXCLUDED_OBSERVATION",
            {issue.code for issue in result.validation.issues},
        )

    def test_duplicate_fx_identity_within_scenario_is_rejected(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        bundle["scenarios"][0]["fx_rates"] = [
            bundle["fx_rates"][0],
            bundle["fx_rates"][0],
        ]
        case = parse_evidence_bundle(bundle)

        with self.assertRaisesRegex(PublicInputError, "must be unique within a scenario"):
            execute_research_case(case)

    def test_bundle_structure_limits_observation_count(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        bundle["observations"] = bundle["observations"] * 501

        with self.assertRaisesRegex(ValueError, "more than 500"):
            parse_evidence_bundle(bundle)

    def test_bundle_rejects_wrong_nested_container_type(self) -> None:
        bundle = json.loads(Path("examples/demo_case.json").read_text(encoding="utf-8"))
        bundle["observations"][0]["unit_price"] = []

        with self.assertRaisesRegex(ValueError, "unit_price must be an object"):
            parse_evidence_bundle(bundle)

    def test_optional_observation_terms_reject_non_string_values(self) -> None:
        for field in (
            "supplier_name",
            "incoterm",
            "incoterm_named_place",
            "incoterm_version",
            "payment_terms",
            "payment_method",
            "product_variant",
        ):
            with self.subTest(field=field):
                bundle = json.loads(
                    Path("examples/demo_case.json").read_text(encoding="utf-8")
                )
                bundle["observations"][0][field] = {"not": "text"}
                with self.assertRaisesRegex(PublicInputError, rf"{field} must be"):
                    parse_evidence_bundle(bundle)

    def test_payment_and_timing_terms_require_exact_public_types(self) -> None:
        invalid_values = (
            ("quote_valid_until", 123, "ISO 8601 string"),
            ("quote_valid_until", "2099-01-01T00:00:00", "timezone offset"),
            ("quote_valid_until", "not-a-date", "valid ISO 8601 timestamp"),
            ("lead_time_days", 1.5, "positive integer"),
            ("lead_time_days", True, "positive integer"),
            ("lead_time_days", 0, "positive integer"),
        )
        for field, value, expected in invalid_values:
            with self.subTest(field=field, value=value):
                bundle = json.loads(
                    Path("examples/demo_case.json").read_text(encoding="utf-8")
                )
                bundle["observations"][0][field] = value
                with self.assertRaisesRegex(PublicInputError, expected):
                    parse_evidence_bundle(bundle)

    def test_assumptions_and_unknowns_require_bounded_nonempty_strings(self) -> None:
        invalid_values = [
            ([{"not": "text"}], "must be a string"),
            (["   "], "cannot be empty"),
            (["x" * 5001], "cannot exceed 5000"),
        ]
        for assumptions, expected in invalid_values:
            with self.subTest(expected=expected):
                bundle = json.loads(
                    Path("examples/demo_case.json").read_text(encoding="utf-8")
                )
                bundle["assumptions"] = assumptions
                with self.assertRaisesRegex(PublicInputError, expected):
                    parse_evidence_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
