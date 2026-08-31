import json
import unittest
from pathlib import Path
from typing import Any

from trade_agent.parsing.request import parse_trade_request


class RequestParsingEvaluationTests(unittest.TestCase):
    def test_evaluation_dataset(self) -> None:
        cases: list[dict[str, Any]] = json.loads(
            Path("evals/request_parsing.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            with self.subTest(case=case["id"]):
                parsed = parse_trade_request(case["input"])
                expected = case["expected"]
                self.assertEqual(parsed.product_name, expected["product_name"])
                self.assertEqual(parsed.quantity, expected["quantity"])
                self.assertEqual(parsed.origin_market, expected["origin_market"])
                self.assertEqual(parsed.destination, expected["destination"])
                self.assertEqual(parsed.can_start_research, expected["can_start_research"])

    def test_parser_rejects_empty_and_oversized_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "required"):
            parse_trade_request("   ")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            parse_trade_request("x" * 5001)
