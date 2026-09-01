import unittest
from dataclasses import replace
from decimal import Decimal

from trade_agent.application.quantity import QuantityPricePoint, analyze_quantity_points
from trade_agent.domain.errors import PublicInputError


def point(
    observation_id: str,
    quantity: int,
    normalized: str | None,
    *,
    supplier: str | None = "Supplier A",
    group: str = "DEVICE:IRR",
) -> QuantityPricePoint:
    return QuantityPricePoint(
        observation_id=observation_id,
        supplier_name=supplier,
        product_name="Product A",
        product_variant="V1",
        product_group_key="product-a:v1",
        comparison_group=group,
        quoted_quantity=quantity,
        minimum_order_quantity=quantity,
        eligible_for_requested_quantity=True,
        original_amount=Decimal(normalized or "10"),
        original_currency="IRR",
        normalized_amount=Decimal(normalized) if normalized is not None else None,
        normalized_currency="IRR" if normalized is not None else None,
        source_name=f"Source {observation_id}",
        source_url=f"https://example.com/{observation_id}",
    )


class QuantityAnalysisTests(unittest.TestCase):
    def test_observed_quantity_points_have_exact_decimal_changes(self) -> None:
        result = analyze_quantity_points(
            500,
            (
                point("q1000", 1000, "8.5"),
                point("q100", 100, "10"),
                point("q500", 500, "9"),
            ),
        )

        self.assertEqual(result.status, "OBSERVED_QUOTES_ONLY")
        self.assertEqual(
            [item.quoted_quantity for item in result.series[0].points],
            [100, 500, 1000],
        )
        self.assertEqual(
            [item.normalized_change_from_previous_percent for item in result.series[0].points],
            [None, Decimal("-10.00"), Decimal("-5.56")],
        )
        self.assertIsNone(result.economic_order_range_min)
        self.assertIsNone(result.economic_order_range_max)

    def test_anonymous_and_incompatible_points_are_not_merged(self) -> None:
        result = analyze_quantity_points(
            500,
            (
                point("anonymous-a", 100, None, supplier=None),
                point("anonymous-b", 500, None, supplier=None),
                point("usd", 500, None, group="DEVICE:USD"),
            ),
        )

        self.assertEqual(result.status, "NO_COMPARABLE_PRICES")
        self.assertEqual(len(result.series), 3)

    def test_different_product_variants_are_not_merged(self) -> None:
        first = point("variant-a", 100, "10")
        second = point("variant-b", 500, "9")
        second = replace(
            second,
            product_variant="V2",
            product_group_key="product-a:v2",
        )

        result = analyze_quantity_points(500, (first, second))

        self.assertEqual(len(result.series), 2)

    def test_empty_input_and_invalid_requested_quantity_are_explicit(self) -> None:
        empty = analyze_quantity_points(10, ())
        self.assertEqual(empty.status, "NO_OBSERVED_QUOTES")

        with self.assertRaisesRegex(PublicInputError, "must be positive"):
            analyze_quantity_points(0, ())


if __name__ == "__main__":
    unittest.main()
