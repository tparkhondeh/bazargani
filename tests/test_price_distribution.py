import unittest
from dataclasses import replace
from decimal import Decimal

from trade_agent.application.price_distribution import (
    DistributionPricePoint,
    analyze_price_distribution,
)
from trade_agent.domain.errors import PublicInputError


def point(observation_id: str, amount: str | None) -> DistributionPricePoint:
    return DistributionPricePoint(
        observation_id=observation_id,
        product_name="Product A",
        product_variant="V1",
        product_group_key="product-a:v1",
        market_layer="WHOLESALE",
        comparison_group="DEVICE:IRR",
        quoted_quantity=500,
        normalized_amount=Decimal(amount) if amount is not None else None,
        normalized_currency="IRR" if amount is not None else None,
        source_url=f"https://example.com/{observation_id}",
    )


class PriceDistributionTests(unittest.TestCase):
    def test_exact_decimal_distribution_and_source_count(self) -> None:
        result = analyze_price_distribution(
            (
                point("high", "14"),
                point("low", "10"),
                point("middle", "12"),
            )
        )

        self.assertEqual(result.status, "OBSERVED_DISTRIBUTIONS")
        group = result.groups[0]
        self.assertEqual(group.minimum_amount, Decimal("10"))
        self.assertEqual(group.median_amount, Decimal("12"))
        self.assertEqual(group.maximum_amount, Decimal("14"))
        self.assertEqual(group.range_amount, Decimal("4"))
        self.assertEqual(group.distinct_source_count, 3)

    def test_even_median_and_incompatible_dimensions_stay_separate(self) -> None:
        first = point("first", "10")
        second = point("second", "11")
        different_quantity = replace(point("quantity", "9"), quoted_quantity=1000)
        different_variant = replace(
            point("variant", "8"),
            product_variant="V2",
            product_group_key="product-a:v2",
        )
        result = analyze_price_distribution(
            (first, second, different_quantity, different_variant)
        )

        self.assertEqual(len(result.groups), 3)
        shared = next(group for group in result.groups if group.observation_count == 2)
        self.assertEqual(shared.median_amount, Decimal("10.50000000"))

    def test_missing_normalization_and_invalid_quantity_are_explicit(self) -> None:
        excluded = analyze_price_distribution((point("missing-fx", None),))
        self.assertEqual(excluded.status, "NO_COMPARABLE_PRICES")
        self.assertEqual(excluded.excluded_observation_ids, ("missing-fx",))

        with self.assertRaisesRegex(PublicInputError, "must be positive"):
            analyze_price_distribution((replace(point("bad", "1"), quoted_quantity=0),))


if __name__ == "__main__":
    unittest.main()
