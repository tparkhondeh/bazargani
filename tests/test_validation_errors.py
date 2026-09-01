import unittest

from fastapi.exceptions import RequestValidationError

from trade_agent.api.validation_errors import (
    MAX_VALIDATION_DETAILS,
    safe_validation_details,
)


class SafeValidationDetailTests(unittest.TestCase):
    def test_input_message_context_and_unsafe_locations_are_not_reflected(self) -> None:
        secret = "COMMERCIAL-SECRET-998877"
        error = RequestValidationError(
            [
                {
                    "type": "int_parsing",
                    "loc": ("body", secret),
                    "msg": f"could not parse {secret}",
                    "input": secret,
                    "ctx": {"secret": secret},
                    "url": f"https://example.invalid/{secret}",
                }
            ]
        )

        details = safe_validation_details(error)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].location, ["body", "field"])
        self.assertEqual(details[0].code, "int_parsing")
        self.assertEqual(details[0].message, "invalid value")
        self.assertNotIn(secret, repr(details))

    def test_details_are_bounded_and_report_omission(self) -> None:
        error = RequestValidationError(
            [
                {
                    "type": "missing",
                    "loc": ("body", f"field_{index}"),
                    "msg": "Field required",
                    "input": {},
                }
                for index in range(MAX_VALIDATION_DETAILS + 10)
            ]
        )

        details = safe_validation_details(error)

        self.assertEqual(len(details), MAX_VALIDATION_DETAILS + 1)
        self.assertEqual(details[0].message, "field is required")
        self.assertEqual(details[-1].code, "additional_errors_omitted")


if __name__ == "__main__":
    unittest.main()
