import asyncio
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Self

import httpx

from app.services.market_data.geo import (
    haversine_distance_m,
    wgs84_to_web_mercator,
    wkt_center_wgs84,
)
from app.services.market_data.schemas import GOVMAP_SOURCE_URL, ComparableSale

GOVMAP_API_BASE = "https://www.govmap.gov.il/api/real-estate"


class MarketDataUnavailable(RuntimeError):
    pass


def subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


class GovMapClient:
    """Small, courteous client for GovMap's public real-estate endpoints."""

    def __init__(
        self, *, timeout_seconds: float = 30.0, retries: int = 3, max_anchors: int = 2
    ):
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.max_anchors = max_anchors
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "ShakedEngine/0.1 comparable-sales research"},
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()

    async def _get_json(
        self, url: str, params: dict[str, str | int] | None = None
    ) -> Any:
        if self._client is None:
            raise RuntimeError("GovMapClient must be used as an async context manager")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = await self._client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise MarketDataUnavailable(
            f"GovMap request failed after {self.retries} attempts: {last_error}"
        )

    async def fetch_nearby_sales(
        self,
        *,
        latitude: float,
        longitude: float,
        city_code: str | None,
        radius_m: int,
        lookback_months: int,
        as_of_date: date,
    ) -> list[ComparableSale]:
        x, y = wgs84_to_web_mercator(latitude, longitude)
        clusters = await self._get_json(f"{GOVMAP_API_BASE}/deals/{x},{y}/{radius_m}")
        if not isinstance(clusters, list):
            raise MarketDataUnavailable(
                "GovMap radius response did not contain a cluster list"
            )

        anchors = sorted(
            (
                cluster
                for cluster in clusters
                if cluster.get("polygon_id") and cluster.get("streetNameHeb") is None
            ),
            key=lambda cluster: int(cluster.get("dealscount") or 0),
            reverse=True,
        )[: self.max_anchors]
        if not anchors:
            anchors = sorted(
                (cluster for cluster in clusters if cluster.get("polygon_id")),
                key=lambda cluster: int(cluster.get("dealscount") or 0),
                reverse=True,
            )[: self.max_anchors]

        params = {
            "limit": 250,
            "startDate": subtract_months(as_of_date, lookback_months).strftime("%Y-%m"),
            "endDate": as_of_date.strftime("%Y-%m"),
        }
        rows: list[dict] = []
        for anchor in anchors:
            endpoint = (
                "neighborhood-deals"
                if anchor.get("streetNameHeb") is None
                else "street-deals"
            )
            payload = await self._get_json(
                f"{GOVMAP_API_BASE}/{endpoint}/{anchor['polygon_id']}",
                params=params,
            )
            if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                rows.extend(payload["data"])

        deduplicated: dict[str, ComparableSale] = {}
        start_date = subtract_months(as_of_date, lookback_months)
        for row in rows:
            sale = self._parse_sale(
                row,
                latitude=latitude,
                longitude=longitude,
                city_code=city_code,
                radius_m=radius_m,
            )
            if sale and start_date <= sale.deal_date <= as_of_date:
                deduplicated[sale.source_deal_id] = sale
        return sorted(
            deduplicated.values(), key=lambda sale: sale.deal_date, reverse=True
        )

    @staticmethod
    def _parse_sale(
        row: dict,
        *,
        latitude: float,
        longitude: float,
        city_code: str | None,
        radius_m: int,
    ) -> ComparableSale | None:
        area = _number(row.get("assetArea"))
        amount = _number(row.get("dealAmount"))
        rooms = _number(row.get("assetRoomNum"))
        property_type = _text(row.get("propertyTypeDescription"))
        deal_nature = _text(row.get("dealNatureDescription"))
        description = f"{property_type or ''} {deal_nature or ''}"
        if "דירה" not in description or any(
            excluded in description for excluded in ("מחסן", "קרקע", "חניה")
        ):
            return None
        if (
            area is None
            or amount is None
            or rooms is None
            or not (20 <= area <= 400 and 1 <= rooms <= 8)
        ):
            return None
        price_per_sqm = amount / area
        if not (5_000 <= price_per_sqm <= 150_000):
            return None

        center = wkt_center_wgs84(_text(row.get("shape")))
        if center is None:
            return None
        sale_latitude, sale_longitude = center
        distance = haversine_distance_m(
            latitude, longitude, sale_latitude, sale_longitude
        )
        if distance > radius_m:
            return None

        try:
            deal_date = datetime.fromisoformat(
                str(row["dealDate"]).replace("Z", "+00:00")
            ).date()
        except (KeyError, TypeError, ValueError):
            return None
        source_id = _text(row.get("dealId")) or _text(row.get("objectid"))
        if source_id is None:
            return None

        return ComparableSale(
            source_deal_id=source_id,
            city_code=city_code,
            settlement_name=_text(row.get("settlementNameHeb")),
            street_name=_text(row.get("streetNameHeb")),
            house_number=_text(row.get("houseNum")),
            neighborhood=_text(row.get("neighborhood")),
            block=_text(row.get("gushNum")),
            parcel=_text(row.get("parcelNum")),
            subparcel=_text(row.get("subParcelNum")),
            deal_date=deal_date,
            deal_amount_ils=amount,
            area_sqm=area,
            rooms=rooms,
            floor=_text(row.get("floorNo")),
            property_type=property_type,
            deal_nature=deal_nature,
            price_per_sqm_ils=round(price_per_sqm, 2),
            latitude=sale_latitude,
            longitude=sale_longitude,
            distance_m=round(distance, 1),
            source_url=GOVMAP_SOURCE_URL,
            raw_json=row,
        )
