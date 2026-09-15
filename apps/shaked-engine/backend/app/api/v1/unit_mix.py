import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.opportunity import Opportunity
from app.models.package import Delivery
from app.models.tenant import User
from app.services.unit_mix.service import UnitMixUnavailable, prepare_unit_mix


router = APIRouter(prefix="/unit-mix", tags=["unit-mix"])


class UnitMixRequest(BaseModel):
    compensation_sqm_per_existing_unit: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Extra sqm granted to every existing apartment. Omit to use the "
            "versioned market-default compensation assumption."
        ),
    )
    persist: bool = Field(
        default=True,
        description="Persist the recommended planned_unit_mix and its valuation snapshot.",
    )


async def _entitled_opportunity(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
    company_id: uuid.UUID,
) -> Opportunity:
    entitled = (
        await session.execute(
            select(Delivery.id).where(
                Delivery.opportunity_id == opportunity_id,
                Delivery.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if entitled is None:
        raise HTTPException(status_code=404, detail="התיק אינו במאגר החברה.")

    opportunity = await session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="התיק אינו במאגר החברה.")
    return opportunity


@router.post("/{opportunity_id}/optimize")
async def optimize_opportunity_unit_mix(
    opportunity_id: uuid.UUID,
    request: UnitMixRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """B15: recalculate the most profitable Herzliya mix for a compensation offer.

    This endpoint performs no scraping. It reuses the delivered opportunity's
    verified apartment schedule, rights assessment, stored comparable sales and
    existing Report-0 assumptions. Calling it again with a different
    compensation value recalculates the mix immediately.
    """

    opportunity = await _entitled_opportunity(
        session, opportunity_id, user.company_id
    )
    try:
        prepared = await prepare_unit_mix(
            session,
            opportunity,
            compensation_sqm_per_existing_unit=request.compensation_sqm_per_existing_unit,
            persist=request.persist,
        )
    except UnitMixUnavailable as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if request.persist:
        await session.commit()

    return {
        "opportunity_id": str(opportunity.id),
        "address": opportunity.address,
        "planned_unit_mix": prepared.planned_unit_mix,
        "planned_unit_mix_meta": prepared.metadata,
        "optimization": prepared.result.model_dump(mode="json"),
    }
