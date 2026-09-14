import unittest
from datetime import date, datetime, timezone

from app.services.market_data.geo import web_mercator_to_wgs84, wgs84_to_web_mercator
from app.services.market_data.govmap import GovMapClient, subtract_months
from app.services.market_data.repository import upsert_transactions
from app.services.market_data.schemas import (
    ComparableSale,
    TargetUnit,
    targets_from_metadata,
)
from app.services.market_data.valuation import calculate_market_valuation


def sale(
    deal_id: str, rooms: float, area: float, price_per_sqm: float, distance: float = 200
) -> ComparableSale:
    return ComparableSale(
        source_deal_id=deal_id,
        deal_date=date(2026, 8, 1),
        deal_amount_ils=area * price_per_sqm,
        area_sqm=area,
        rooms=rooms,
        price_per_sqm_ils=price_per_sqm,
        distance_m=distance,
    )


class GeoTests(unittest.TestCase):
    def test_web_mercator_round_trip(self) -> None:
        x, y = wgs84_to_web_mercator(32.16, 34.84)
        latitude, longitude = web_mercator_to_wgs84(x, y)
        self.assertAlmostEqual(latitude, 32.16, places=6)
        self.assertAlmostEqual(longitude, 34.84, places=6)

    def test_subtract_months_handles_month_end(self) -> None:
        self.assertEqual(subtract_months(date(2026, 3, 31), 1), date(2026, 2, 28))


class GovMapParsingTests(unittest.TestCase):
    def test_rejects_non_apartment_and_keeps_valid_local_sale(self) -> None:
        latitude, longitude = 32.16, 34.84
        x, y = wgs84_to_web_mercator(latitude, longitude)
        base = {
            "objectid": 1,
            "dealId": 123,
            "dealDate": "2026-08-12T00:00:00.000Z",
            "assetArea": 100,
            "dealAmount": 3_000_000,
            "assetRoomNum": 4,
            "propertyTypeDescription": "דירה",
            "dealNatureDescription": "דירה בבית קומות",
            "shape": f"MULTIPOLYGON((({x} {y},{x + 5} {y},{x + 5} {y + 5},{x} {y})))",
        }
        parsed = GovMapClient._parse_sale(
            base,
            latitude=latitude,
            longitude=longitude,
            city_code="herzliya",
            radius_m=500,
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.price_per_sqm_ils, 30_000)

        storage = {**base, "dealId": 124, "propertyTypeDescription": "מחסן"}
        self.assertIsNone(
            GovMapClient._parse_sale(
                storage,
                latitude=latitude,
                longitude=longitude,
                city_code="herzliya",
                radius_m=500,
            )
        )


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transaction_upsert_is_concurrency_safe(self) -> None:
        class CapturingSession:
            statement = None

            async def execute(self, statement):
                self.statement = statement

        session = CapturingSession()
        await upsert_transactions(session, [sale("same-deal", 4, 100, 35_000)])
        sql = str(session.statement.compile()).upper()
        self.assertIn("ON CONFLICT", sql)
        self.assertIn("DO UPDATE", sql)


class ValuationTests(unittest.TestCase):
    def test_invalid_unit_mix_is_explicit_and_cannot_create_a_blended_price(
        self,
    ) -> None:
        targets, state, warning = targets_from_metadata(
            {"planned_unit_mix": [{"rooms": 4}]}
        )
        self.assertEqual(state, "provided")
        self.assertIsNone(warning)
        self.assertIsNone(targets[0].units)

        targets, state, warning = targets_from_metadata({"planned_unit_mix": "4 rooms"})
        self.assertEqual(state, "invalid")
        self.assertIsNotNone(warning)
        self.assertTrue(all(target.units is None for target in targets))

    def test_estimates_by_rooms_and_removes_extreme_outlier(self) -> None:
        transactions = [
            sale("a", 4, 90, 30_000),
            sale("b", 4, 92, 31_000),
            sale("c", 4, 94, 32_000),
            sale("d", 4, 96, 33_000),
            sale("e", 4, 98, 34_000),
            sale("outlier", 4, 95, 100_000),
        ]
        valuation = calculate_market_valuation(
            transactions,
            [TargetUnit(rooms=4, area_sqm=95)],
            as_of_date=date(2026, 9, 1),
            lookback_months=12,
            radius_m=500,
            fetched_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        estimate = valuation.room_estimates[0]
        self.assertEqual(estimate.comparable_count, 5)
        self.assertEqual(estimate.base_price_per_sqm_ils, 32_000)
        self.assertEqual(estimate.estimated_total_price_ils, 3_040_000)
        self.assertIsNone(valuation.blended_price_per_sqm_ils)

    def test_blends_only_with_explicit_complete_unit_mix(self) -> None:
        transactions = [
            sale("3a", 3, 75, 30_000),
            sale("3b", 3, 76, 31_000),
            sale("4a", 4, 100, 40_000),
            sale("4b", 4, 101, 41_000),
        ]
        valuation = calculate_market_valuation(
            transactions,
            [
                TargetUnit(rooms=3, area_sqm=75, units=2),
                TargetUnit(rooms=4, area_sqm=100, units=1),
            ],
            as_of_date=date(2026, 9, 1),
            lookback_months=12,
            radius_m=500,
        )
        self.assertTrue(valuation.is_unit_mix_adjusted)
        self.assertAlmostEqual(valuation.blended_price_per_sqm_ils, 34_000)


if __name__ == "__main__":
    unittest.main()
