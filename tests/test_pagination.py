import unittest
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from trade_agent.application.pagination import decode_cursor, encode_cursor


class PaginationTests(unittest.TestCase):
    def test_cursor_round_trip_normalizes_time_and_uuid(self) -> None:
        record_id = str(uuid4())
        created_at = datetime(
            2026,
            9,
            1,
            12,
            30,
            tzinfo=timezone(timedelta(hours=3, minutes=30)),
        )

        decoded = decode_cursor(encode_cursor(created_at, record_id))

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.created_at, created_at.astimezone(UTC))
        self.assertEqual(decoded.record_id, record_id)

    def test_naive_database_timestamp_is_encoded_as_utc(self) -> None:
        created_at = datetime(2026, 9, 1, 12, 30)

        decoded = decode_cursor(encode_cursor(created_at, str(uuid4())))

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.created_at.tzinfo, UTC)

    def test_malformed_or_oversized_cursor_is_rejected(self) -> None:
        for cursor in ("not-a-cursor", "x" * 513, ""):
            with self.subTest(cursor_length=len(cursor)), self.assertRaisesRegex(
                ValueError, "invalid pagination cursor"
            ):
                decode_cursor(cursor)


if __name__ == "__main__":
    unittest.main()
