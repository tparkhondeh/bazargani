import unittest
from pathlib import Path

from trade_agent.application.research import execute_research_case
from trade_agent.providers.evidence_bundle import load_evidence_bundle
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


if __name__ == "__main__":
    unittest.main()
