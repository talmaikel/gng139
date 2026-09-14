from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

GOVMAP_SOURCE_URL = "https://www.govmap.gov.il/?lay=nadlan"


class ValuationStatus(str, Enum):
    ESTIMATED = "estimated"
    INSUFFICIENT_DATA = "insufficient_data"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class TargetUnit(BaseModel):
    rooms: float = Field(gt=0, le=10)
    area_sqm: float | None = Field(default=None, gt=0)
    units: int | None = Field(default=None, gt=0)


DEFAULT_TARGETS = [TargetUnit(rooms=3), TargetUnit(rooms=4), TargetUnit(rooms=5)]


def targets_from_metadata(
    metadata: dict | None,
) -> tuple[list[TargetUnit], str, str | None]:
    raw_mix = (metadata or {}).get("planned_unit_mix")
    if raw_mix is None:
        return [target.model_copy() for target in DEFAULT_TARGETS], "absent", None
    if not isinstance(raw_mix, list) or not raw_mix:
        return (
            [target.model_copy() for target in DEFAULT_TARGETS],
            "invalid",
            "planned_unit_mix is present but invalid; no project-wide price was calculated.",
        )
    try:
        targets = [TargetUnit.model_validate(item) for item in raw_mix]
    except (TypeError, ValueError):
        return (
            [target.model_copy() for target in DEFAULT_TARGETS],
            "invalid",
            "planned_unit_mix is present but invalid; no project-wide price was calculated.",
        )
    return targets, "provided", None


class ComparableSale(BaseModel):
    source: str = "govmap"
    source_deal_id: str
    city_code: str | None = None
    settlement_name: str | None = None
    street_name: str | None = None
    house_number: str | None = None
    neighborhood: str | None = None
    block: str | None = None
    parcel: str | None = None
    subparcel: str | None = None
    deal_date: date
    deal_amount_ils: float = Field(gt=0)
    area_sqm: float = Field(gt=0)
    rooms: float = Field(gt=0)
    floor: str | None = None
    property_type: str | None = None
    deal_nature: str | None = None
    price_per_sqm_ils: float = Field(gt=0)
    latitude: float | None = None
    longitude: float | None = None
    distance_m: float | None = None
    source_url: str = GOVMAP_SOURCE_URL
    raw_json: dict = Field(default_factory=dict, exclude=True)

    @property
    def address(self) -> str:
        parts = [self.street_name, self.house_number, self.settlement_name]
        return " ".join(str(part) for part in parts if part)


class RoomPriceEstimate(BaseModel):
    rooms: float
    target_area_sqm: float | None = None
    target_units: int | None = None
    comparable_count: int
    low_price_per_sqm_ils: float | None = None
    base_price_per_sqm_ils: float | None = None
    high_price_per_sqm_ils: float | None = None
    estimated_total_price_ils: float | None = None
    confidence: Confidence
    comparable_deal_ids: list[str] = Field(default_factory=list)


class MarketValuation(BaseModel):
    source: str = "govmap"
    source_url: str = GOVMAP_SOURCE_URL
    status: ValuationStatus
    as_of_date: date
    fetched_at: datetime
    lookback_months: int
    radius_m: int
    comparable_count: int
    comparable_sales: list[ComparableSale]
    room_estimates: list[RoomPriceEstimate]
    blended_price_per_sqm_ils: float | None = None
    is_unit_mix_adjusted: bool = False
    warnings: list[str] = Field(default_factory=list)


class MarketDataResult(BaseModel):
    valuation: MarketValuation
    transactions: list[ComparableSale] = Field(default_factory=list)
    cache_hit: bool = False
