import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.queue import enqueue
from app.core.security import current_active_user
from app.evidence import Certainty
from app.models.dwelling_unit import DwellingUnit
from app.models.opportunity import Opportunity
from app.models.package import Delivery
from app.models.task_queue import TaskQueue
from app.models.tenant import User
from app.services.dwelling_units import load_units, resolve_existing_unit_area

router = APIRouter(prefix="/dossiers", tags=["dossiers"])


class BatchDossierRequest(BaseModel):
    opportunity_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)
    # B2: the developer's own construction cost beats the appraisers'
    # regional survey fallback (see services/economic/construction_costs.py)
    # whenever supplied. One figure for the whole batch -- a developer
    # running several candidates at once is pricing them against the same
    # contractor quote, not a different one per parcel.
    construction_cost_per_sqm_ils: float | None = Field(
        default=None, gt=0,
        description="Developer-supplied construction cost per sqm (ILS), applied to every opportunity in the batch",
    )


class GenerateDossierRequest(BaseModel):
    construction_cost_per_sqm_ils: float | None = Field(
        default=None, gt=0,
        description="Developer-supplied construction cost per sqm (ILS). "
                     "Overrides the appraisers' regional survey fallback (B2)",
    )


class DwellingUnitReviewRequest(BaseModel):
    action: Literal["confirm", "reject"]
    unit_label: str | None = Field(default=None, max_length=40)
    floor: str | None = Field(default=None, max_length=20)
    area_sqm: float | None = Field(default=None, ge=15, le=400)


def _unit_payload(unit: DwellingUnit) -> dict[str, Any]:
    return {
        "id": str(unit.id),
        "source_key": unit.source_key,
        "unit_label": unit.unit_label,
        "floor": unit.floor,
        "area_sqm": unit.area_sqm,
        "balcony_area_sqm": unit.balcony_area_sqm,
        "rooms": unit.rooms,
        "certainty": unit.certainty.value,
        "requires_human_review": unit.requires_human_review,
        "source_url": unit.source_url,
        "retrieved_at": unit.retrieved_at.isoformat() if unit.retrieved_at else None,
        "location": unit.location,
        "method": unit.method,
        "raw_text": unit.raw_text,
    }


def _resolution_payload(resolution) -> dict[str, Any]:
    return {
        "average_existing_unit_sqm": resolution.average_existing_unit_sqm,
        "source": resolution.source,
        "certainty": resolution.certainty.value,
        "per_unit_detail_available": resolution.per_unit_detail_available,
        "unit_count": resolution.unit_count,
        "schedule_complete": resolution.schedule_complete,
        "has_unit_count_conflict": resolution.has_unit_count_conflict,
        "may_decide": resolution.may_decide,
        "notes": resolution.notes,
    }


def _apply_dwelling_review(unit: DwellingUnit, review: DwellingUnitReviewRequest) -> None:
    """Apply a human decision without weakening the provenance gate.

    A row may become MANUALLY_VERIFIED only when it still carries the source
    URL, retrieval time and source location that let the reviewer trace the
    value back to the permit image. Correcting label/floor/area is allowed;
    the original OCR/AI text remains in raw_text for audit.
    """
    if review.action == "reject":
        unit.area_sqm = None
        unit.certainty = Certainty.MISSING
        # Keep it reviewable so the next extraction run may replace the bad
        # candidate. Confirmed rows are deliberately protected from replacement.
        unit.requires_human_review = True
        unit.method = "manual_rejected"
        return

    area = review.area_sqm if review.area_sqm is not None else unit.area_sqm
    if area is None:
        raise HTTPException(status_code=422, detail="אי אפשר לאשר דירה בלי שטח.")
    if not unit.source_url or not unit.retrieved_at or not unit.location:
        raise HTTPException(
            status_code=422,
            detail="אי אפשר לאשר נתון ללא מקור, מועד ומיקום במסמך.",
        )

    if review.unit_label is not None:
        unit.unit_label = review.unit_label.strip() or None
    if review.floor is not None:
        unit.floor = review.floor.strip() or None
    unit.area_sqm = area
    unit.certainty = Certainty.MANUALLY_VERIFIED
    unit.requires_human_review = False
    unit.method = "manual_review"


async def _reviewable_opportunity(
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
        # Same non-enumerating behavior as the dossier itself (ACC-08).
        raise HTTPException(status_code=404, detail="התיק אינו במאגר החברה.")

    opportunity = await session.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="התיק אינו במאגר החברה.")
    return opportunity


async def _dwelling_review_state(
    session: AsyncSession,
    opportunity: Opportunity,
) -> dict[str, Any]:
    units = await load_units(session, opportunity.id)
    resolution = resolve_existing_unit_area(
        units,
        municipal_unit_count=opportunity.existing_units,
        existing_area_sqm=None,
    )
    return {
        "opportunity_id": str(opportunity.id),
        "address": opportunity.address,
        "municipal_unit_count": opportunity.existing_units,
        "units": [_unit_payload(unit) for unit in units],
        "resolution": _resolution_payload(resolution),
    }


@router.get("/{opportunity_id}/dwelling-units")
async def get_dwelling_units_for_review(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Human-review queue for B3: extracted apartment rows plus current gate state."""
    opportunity = await _reviewable_opportunity(session, opportunity_id, user.company_id)
    return await _dwelling_review_state(session, opportunity)


@router.patch("/{opportunity_id}/dwelling-units/{unit_id}")
async def review_dwelling_unit(
    opportunity_id: uuid.UUID,
    unit_id: uuid.UUID,
    review: DwellingUnitReviewRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Confirm/correct or reject one extracted apartment against the source scan."""
    opportunity = await _reviewable_opportunity(session, opportunity_id, user.company_id)
    unit = (
        await session.execute(
            select(DwellingUnit).where(
                DwellingUnit.id == unit_id,
                DwellingUnit.opportunity_id == opportunity_id,
            )
        )
    ).scalar_one_or_none()
    if unit is None:
        raise HTTPException(status_code=404, detail="הדירה לא נמצאה בתיק הזה.")

    _apply_dwelling_review(unit, review)
    await session.commit()
    return await _dwelling_review_state(session, opportunity)


@router.post("/generate-batch")
async def generate_dossier_batch(
    request: BatchDossierRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Queue the on-demand final-stage pipeline for at most three selected opportunities."""
    if len(set(request.opportunity_ids)) != len(request.opportunity_ids):
        raise HTTPException(status_code=422, detail="opportunity_ids must be unique")

    found_ids = set(
        (
            await session.execute(
                select(Opportunity.id).where(
                    Opportunity.id.in_(request.opportunity_ids)
                )
            )
        ).scalars()
    )
    missing_ids = [
        str(item) for item in request.opportunity_ids if item not in found_ids
    ]
    if missing_ids:
        raise HTTPException(
            status_code=404, detail={"missing_opportunity_ids": missing_ids}
        )

    batch_payload: dict[str, Any] = {}
    if request.construction_cost_per_sqm_ils is not None:
        batch_payload["construction_cost_per_sqm_ils"] = request.construction_cost_per_sqm_ils

    tasks = [
        await enqueue(
            session,
            task_type="generate_dossier",
            payload={"opportunity_id": str(opportunity_id), **batch_payload},
            company_id=user.company_id,
        )
        for opportunity_id in request.opportunity_ids
    ]
    await session.commit()
    return {
        "tasks": [
            {
                "opportunity_id": str(opportunity_id),
                "task_id": str(task.id),
                "status": task.status,
            }
            for opportunity_id, task in zip(request.opportunity_ids, tasks, strict=True)
        ]
    }


@router.post("/{opportunity_id}/generate")
async def generate_dossier(
    opportunity_id: uuid.UUID,
    request: GenerateDossierRequest | None = None,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Enqueue an asynchronous dossier-generation job for one opportunity."""
    payload: dict[str, Any] = {"opportunity_id": str(opportunity_id)}
    if request and request.construction_cost_per_sqm_ils is not None:
        payload["construction_cost_per_sqm_ils"] = request.construction_cost_per_sqm_ils

    task = await enqueue(
        session,
        task_type="generate_dossier",
        payload=payload,
        company_id=user.company_id,
    )
    await session.commit()
    return {"task_id": str(task.id), "status": task.status}


@router.get("/status/{task_id}")
async def get_dossier_status(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    task = (await session.execute(select(TaskQueue).where(TaskQueue.id == task_id))).scalar_one_or_none()
    if task is None or task.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Dossier job not found")
    return {
        "task_id": str(task.id),
        "status": task.status,
        "attempts": task.attempts,
        "result": task.result,
        "error": task.error,
    }
