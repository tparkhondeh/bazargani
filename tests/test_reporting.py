import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from trade_agent.application.research import execute_research_case
from trade_agent.providers.evidence_bundle import load_evidence_bundle
from trade_agent.reporting.markdown import render_markdown


class MarkdownReportingTests(unittest.TestCase):
    def test_untrusted_fields_cannot_inject_html_headings_or_links(self) -> None:
        case = load_evidence_bundle(Path("examples/demo_case.json"))
        observation = case.observations[0]
        hostile_evidence = replace(
            observation.evidence,
            source_name="source](https://evil.example)\n# forged heading",
            source_url="https://example.com/a) [evil](https://evil.example",
        )
        hostile_observation = replace(
            observation,
            supplier_name='<img src=x onerror="steal()">',
            incoterm_named_place=(
                "</li><script>incoterm()</script> [forged](https://evil.example)"
            ),
            evidence=hostile_evidence,
        )
        hostile_scenarios = tuple(
            replace(
                scenario,
                fx_rates=tuple(
                    replace(rate, evidence=hostile_evidence)
                    for rate in scenario.fx_rates
                ),
                costs=tuple(
                    replace(cost, label_fa="</li><script>steal()</script>")
                    for cost in scenario.costs
                ),
            )
            for scenario in case.scenarios
        )
        hostile_case = replace(
            case,
            case_id="case`id",
            product_name="<script>steal()</script>\n# forged title",
            destination="[click](https://evil.example)",
            observations=(hostile_observation,),
            scenarios=hostile_scenarios,
            assumptions=("<iframe src=https://evil.example></iframe>",),
            unknowns=("[click](https://evil.example)",),
        )
        result = execute_research_case(
            hostile_case,
            evaluated_at=datetime(2026, 9, 1, tzinfo=UTC),
        )

        report = render_markdown(result)

        self.assertNotIn("<script", report)
        self.assertNotIn("<img", report)
        self.assertNotIn("<iframe", report)
        self.assertNotIn("<script>incoterm", report)
        self.assertNotIn("\n# forged", report)
        self.assertIn(
            r"&lt;script&gt;steal\(\)&lt;/script&gt; \# forged title",
            report,
        )
        self.assertIn(
            r"source\]\(https://evil.example\) \# forged heading",
            report,
        )
        self.assertIn(
            "(https://example.com/a%29%20%5Bevil%5D%28https://evil.example)",
            report,
        )
        self.assertNotIn("[click](https://evil.example)", report)
        self.assertIn("``case`id``", report)
        self.assertIn(
            r"&lt;/li&gt;&lt;script&gt;incoterm\(\)&lt;/script&gt; "
            r"\[forged\]\(https://evil.example\)",
            report,
        )


if __name__ == "__main__":
    unittest.main()
