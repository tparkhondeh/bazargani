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
                self.assertEqual(
                    parsed.field_conflicts,
                    {
                        field: tuple(values)
                        for field, values in expected.get("field_conflicts", {}).items()
                    },
                )
                self.assertEqual(parsed.can_start_research, expected["can_start_research"])

    def test_parser_rejects_empty_and_oversized_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "required"):
            parse_trade_request("   ")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            parse_trade_request("x" * 5001)
        with self.assertRaisesRegex(ValueError, "location exceeds"):
            parse_trade_request(
                "100 units pump from " + ("x" * 101) + " delivered to Tehran"
            )

    def test_location_aliases_deduplicate_and_ambiguous_to_is_not_a_destination(self) -> None:
        aliases = parse_trade_request(
            "100 units pump from Dubai and from UAE delivered to Tehran"
        )
        ambiguous = parse_trade_request("100 units pump ready to ship")

        self.assertEqual(aliases.origin_market, "UAE")
        self.assertEqual(aliases.field_conflicts, {})
        self.assertIsNone(ambiguous.destination)
        self.assertIn(
            "مقصد نهایی محاسبه بهای تمام‌شده کجاست؟",
            ambiguous.critical_questions,
        )
