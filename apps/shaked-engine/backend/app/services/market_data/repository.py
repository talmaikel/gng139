import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data import MarketValuationRun, PropertyTransaction
from app.services.market_data.schemas import ComparableSale, MarketValuation


async def find_fresh_valuation(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    max_age_days: int,
    radius_m: int,
    lookback_months: int,
    parameters: dict,
) -> MarketValuation | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    stmt = (
        select(MarketValuationRun)
        .where(
            MarketValuationRun.opportunity_id == opportunity_id,
            MarketValuationRun.created_at >= cutoff,
            MarketValuationRun.radius_m == radius_m,
            MarketValuationRun.lookback_months == lookback_months,
            MarketValuationRun.parameters_json == parameters,
        )
        .order_by(MarketValuationRun.created_at.desc())
        .limit(1)
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    return MarketValuation.model_validate(run.result_json) if run else None


async def upsert_transactions(session: AsyncSession, sales: list[ComparableSale]) -> None:
    if not sales:
        return

    rows = []
    for sale in sales:
        values = sale.model_dump(exclude={"distance_m", "raw_json"})
        values["raw_json"] = sale.raw_json
        rows.append(values)

    statement = insert(PropertyTransaction).values(rows)
    update_columns = {
        column: getattr(statement.excluded, column)
        for column in rows[0]
        if column not in {"source", "source_deal_id"}
    }
    update_columns["last_seen_at"] = func.now()
    statement = statement.on_conflict_do_update(
        constraint="uq_property_transactions_source_deal",
        set_=update_columns,
    )
    await session.execute(statement)


def add_valuation_run(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    valuation: MarketValuation,
    parameters: dict,
) -> None:
    session.add(
        MarketValuationRun(
            opportunity_id=opportunity_id,
            source=valuation.source,
            as_of_date=valuation.as_of_date,
            lookback_months=valuation.lookback_months,
            radius_m=valuation.radius_m,
            comparable_count=valuation.comparable_count,
            source_url=valuation.source_url,
            parameters_json=parameters,
            result_json=valuation.model_dump(mode="json"),
            fetched_at=valuation.fetched_at,
        )
    )


async def find_latest_valuation(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    max_age_days: int,
) -> MarketValuation | None:
    """The most recent valuation for this parcel, whatever it was run with.

    Distinct from `find_fresh_valuation`, and deliberately so. That one is a
    *cache* lookup: it must match radius, lookback and the exact unit-mix
    parameters, because a hit lets the caller skip a live fetch and a
    different mix is a different question.

    This one is a *reader*. The dossier endpoint is not allowed to fetch --
    no network at request time -- so it asks a narrower question: is there a
    recent valuation for this parcel at all? A valuation run for a slightly
    different unit mix is still a far better price than a city-wide estimate,
    and the dossier reports the mix it was run with either way.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    stmt = (
        select(MarketValuationRun)
        .where(
            MarketValuationRun.opportunity_id == opportunity_id,
            MarketValuationRun.created_at >= cutoff,
        )
        .order_by(MarketValuationRun.created_at.desc())
        .limit(1)
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    return MarketValuation.model_validate(run.result_json) if run else None
