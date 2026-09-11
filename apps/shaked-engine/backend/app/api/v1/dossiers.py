import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.queue import enqueue
from app.core.security import current_active_user
from app.models.task_queue import TaskQueue
from app.models.tenant import User

router = APIRouter(prefix="/dossiers", tags=["dossiers"])


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
