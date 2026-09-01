import json
import unittest
from dataclasses import replace
from pathlib import Path

from trade_agent.application.research import execute_research_case
from trade_agent.domain.errors import PublicInputError
from trade_agent.providers.evidence_bundle import load_evidence_bundle, parse_evidence_bundle
from trade_agent.reporting.markdown import render_markdown


class EvidenceBundleTests(unittest.TestCase):
    def test_demo_bundle_runs_end_to_end(self) -> None:
        case = load_evidence_bundle(Path("examples/demo_case.json"))
        result = execute_research_case(case)
        report = render_markdown(result)
        self.assertEqual(len(result.scenarios), 3)
        self.assertIn("DEMO-NOT-MARKET-DATA", report)
        self.assertIn("مجهولات", report)
        self.assertIn("https://example.com/demo-supplier", report)
        self.assertIn("EXACT_VARIANT", report)
        self.assertIn("تطبیق محصول", report)
        self.assertIn("رتبه‌بندی پیشنهادهای تأمین‌کننده", report)
        self.assertIn(r"supplier\_reliability", report)
        self.assertIn("حساسیت سناریوها", report)
        self.assertIn("25.51%", report)
        self.assertIn("نرخ‌های ارز سناریوها", report)
        self.assertEqual(report.count("1 `USD` = 100 `IRR`"), 3)

    def test_duplicate_scenario_names_are_rejected_before_calculation(self) -> None:
        case = load_evidence_bundle(Path("examples/demo_case.json"))
        duplicate = replace(case, scenarios=(*case.scenarios, case.scenarios[1]))

        with self.assertRaisesRegex(ValueError, "scenario names must be unique"):
            execute_research_case(duplicate)

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


if __name__ == "__main__":
    unittest.main()
