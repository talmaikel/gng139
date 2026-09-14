import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.queue import enqueue
from app.core.security import current_active_user
from app.models.opportunity import Opportunity
from app.models.task_queue import TaskQueue
from app.models.tenant import User

router = APIRouter(prefix="/dossiers", tags=["dossiers"])


class BatchDossierRequest(BaseModel):
    opportunity_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


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

    tasks = [
        await enqueue(
            session,
            task_type="generate_dossier",
            payload={"opportunity_id": str(opportunity_id)},
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
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Enqueue an asynchronous dossier-generation job for one opportunity."""
    task = await enqueue(
        session,
        task_type="generate_dossier",
        payload={"opportunity_id": str(opportunity_id)},
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
