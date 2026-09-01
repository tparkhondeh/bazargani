import unittest

from trade_agent.application.incoterm_coverage import (
    IncotermEvidencePoint,
    summarize_incoterm_coverage,
)
from trade_agent.domain.errors import PublicInputError


def point(
    observation_id: str,
    incoterm: str | None,
    supplier_name: str | None = "Supplier Fixture",
    named_place: str | None = "Fixture Port",
    version: str | None = "2020",
) -> IncotermEvidencePoint:
    return IncotermEvidencePoint(
        observation_id=observation_id,
        incoterm=incoterm,
        incoterm_named_place=named_place,
        incoterm_version=version,
        supplier_name=supplier_name,
        source_url=f"https://example.com/{observation_id}",
    )


class IncotermCoverageTests(unittest.TestCase):
    def test_groups_recognized_and_unknown_declarations_without_comparing_them(self) -> None:
        result = summarize_incoterm_coverage(
            (
                point("obs-fob-2", "fob", "Supplier B", "Port B", "  "),
                point("obs-custom", "ZZZ", None),
                point("obs-fob-1", "FOB", "Supplier A", "Port A", "2020"),
                point("obs-missing", None, named_place=None, version=None),
            )
        )

        self.assertEqual(result.status, "OBSERVED_INCOTERM_COVERAGE")
        self.assertEqual(result.reference_version, "INCOTERMS_2020")
        self.assertEqual(result.observed_recognized_codes, ("FOB",))
        self.assertEqual(result.unrecognized_declared_codes, ("ZZZ",))
        self.assertEqual([group.code for group in result.groups], ["FOB", "ZZZ"])
        self.assertTrue(result.groups[0].recognized)
        self.assertEqual(result.groups[0].offer_count, 2)
        self.assertEqual(result.groups[0].named_supplier_count, 2)
        self.assertEqual(result.groups[0].named_places, ("Port A", "Port B"))
        self.assertEqual(result.groups[0].declared_versions, ("2020",))
        self.assertEqual(result.groups[0].named_place_observation_count, 2)
        self.assertEqual(result.groups[0].version_observation_count, 1)
        self.assertEqual(result.groups[0].complete_terms_observation_count, 1)
        self.assertFalse(result.groups[1].recognized)
        self.assertEqual(result.missing_incoterm_observation_ids, ("obs-missing",))
        self.assertEqual(result.missing_named_place_observation_ids, ())
        self.assertEqual(result.missing_version_observation_ids, ("obs-fob-2",))
        self.assertEqual(
            result.comparison_status,
            "WITHHELD_NO_INCOTERM_SCENARIOS",
        )

    def test_empty_and_undeclared_statuses_are_distinct(self) -> None:
        self.assertEqual(
            summarize_incoterm_coverage(()).status,
            "NO_PRICE_OBSERVATIONS",
        )
        missing = summarize_incoterm_coverage(
            (
                point("obs-empty", "  ", named_place=None, version=None),
                point("obs-none", None, named_place=None, version=None),
            )
        )
        self.assertEqual(missing.status, "NO_DECLARED_INCOTERMS")
        self.assertEqual(
            missing.missing_incoterm_observation_ids,
            ("obs-empty", "obs-none"),
        )

    def test_duplicate_observation_ids_fail_closed(self) -> None:
        with self.assertRaisesRegex(PublicInputError, "must be unique"):
            summarize_incoterm_coverage((point("duplicate", "EXW"), point("duplicate", "FOB")))


if __name__ == "__main__":
    unittest.main()
