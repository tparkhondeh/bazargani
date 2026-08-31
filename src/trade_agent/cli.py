from __future__ import annotations

import argparse
from pathlib import Path

from trade_agent.application.research import execute_research_case
from trade_agent.providers.evidence_bundle import load_evidence_bundle
from trade_agent.reporting.markdown import render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate an evidence-backed trade case")
    parser.add_argument("case", type=Path, help="Path to a validated evidence bundle JSON")
    parser.add_argument("--output", type=Path, help="Write Markdown report to this path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = render_markdown(execute_research_case(load_evidence_bundle(args.case)))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(args.output.resolve())
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
