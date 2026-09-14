import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.govmap import GovMapClient
from app.services.market_data.repository import (
    add_valuation_run,
    find_fresh_valuation,
    upsert_transactions,
)
from app.services.market_data.schemas import (
    MarketDataResult,
    TargetUnit,
    targets_from_metadata,
)
from app.services.market_data.valuation import calculate_market_valuation


def market_valuation_parameters(
    metadata: dict | None,
) -> tuple[list[TargetUnit], dict, str | None]:
    """Build the canonical parameter set used to identify a valuation snapshot.

    Dossier generation and market-data refresh must use the exact same parameter
    fingerprint. Keeping it here prevents the final delivered dossier from
    looking up a different cache key than the one B1 persisted.
    """
    targets, unit_mix_state, unit_mix_warning = targets_from_metadata(metadata)
    parameters = {
        "unit_mix_state": unit_mix_state,
        "targets": [target.model_dump(mode="json") for target in targets],
    }
    return targets, parameters, unit_mix_warning


async def get_or_refresh_market_valuation(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    latitude: float,
    longitude: float,
    city_code: str,
    metadata: dict | None,
    as_of_date: date | None = None,
    radius_m: int = 500,
    lookback_months: int = 12,
    cache_days: int = 7,
) -> MarketDataResult:
    targets, parameters, unit_mix_warning = market_valuation_parameters(metadata)
    cached = await find_fresh_valuation(
        session,
        opportunity_id=opportunity_id,
        max_age_days=cache_days,
        radius_m=radius_m,
        lookback_months=lookback_months,
        parameters=parameters,
    )
    if cached:
        return MarketDataResult(valuation=cached, cache_hit=True)

    as_of_date = as_of_date or datetime.now(timezone.utc).date()
    async with GovMapClient() as client:
        sales = await client.fetch_nearby_sales(
            latitude=latitude,
            longitude=longitude,
            city_code=city_code,
            radius_m=radius_m,
            lookback_months=lookback_months,
            as_of_date=as_of_date,
        )
    valuation = calculate_market_valuation(
        sales,
        targets,
        as_of_date=as_of_date,
        lookback_months=lookback_months,
        radius_m=radius_m,
    )
    if unit_mix_warning:
        valuation.warnings.insert(0, unit_mix_warning)
    await upsert_transactions(session, sales)
    add_valuation_run(
        session,
        opportunity_id=opportunity_id,
        valuation=valuation,
        parameters=parameters,
    )
    await session.flush()
    return MarketDataResult(valuation=valuation, transactions=sales)
