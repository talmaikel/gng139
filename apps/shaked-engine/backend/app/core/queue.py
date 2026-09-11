"""
Pure-PostgreSQL background job queue.

No Redis / RabbitMQ. A row in `task_queue` is claimed atomically with
`SELECT ... FOR UPDATE SKIP LOCKED`, so any number of worker processes can poll
the same table concurrently without ever blocking on, or double-processing, a row.

Usage:
    from app.core.queue import TaskQueueWorker

    worker = TaskQueueWorker()
    worker.register("generate_dossier", generate_dossier_handler)
    await worker.run_forever()
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.task_queue import TaskQueue, TaskStatus

logger = logging.getLogger("shaked.queue")

TaskHandler = Callable[[dict], Awaitable[dict]]


async def enqueue(session: AsyncSession, task_type: str, payload: dict, company_id=None) -> TaskQueue:
    task = TaskQueue(task_type=task_type, payload=payload, company_id=company_id)
    session.add(task)
    await session.flush()
    return task


async def _claim_next_task(session: AsyncSession, task_types: list[str] | None) -> TaskQueue | None:
    stmt = (
        select(TaskQueue)
        .where(TaskQueue.status == TaskStatus.PENDING)
        .order_by(TaskQueue.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task_types:
        stmt = stmt.where(TaskQueue.task_type.in_(task_types))

    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        return None

    task.status = TaskStatus.IN_PROGRESS
    task.attempts += 1
    await session.flush()
    return task


class TaskQueueWorker:
    def __init__(self, poll_interval_seconds: float = 2.0):
        self.poll_interval_seconds = poll_interval_seconds
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        self._handlers[task_type] = handler

    async def _process_once(self) -> bool:
        """Claim and run a single task. Returns True if a task was processed."""
        async with AsyncSessionLocal() as session:
            async with session.begin():
                task = await _claim_next_task(session, task_types=list(self._handlers.keys()))
                if task is None:
                    return False
                task_id, task_type, payload = task.id, task.task_type, task.payload

            handler = self._handlers[task_type]
            try:
                task_result = await handler(payload)
                async with session.begin():
                    await session.execute(
                        update(TaskQueue)
                        .where(TaskQueue.id == task_id)
                        .values(status=TaskStatus.DONE, result=task_result, error=None)
                    )
            except Exception as exc:  # noqa: BLE001 - persist any failure onto the row
                logger.exception("Task %s (%s) failed", task_id, task_type)
                async with session.begin():
                    await session.execute(
                        update(TaskQueue)
                        .where(TaskQueue.id == task_id)
                        .values(status=TaskStatus.FAILED, error=str(exc))
                    )
        return True

    async def run_forever(self) -> None:
        logger.info("Queue worker started, handling task types: %s", list(self._handlers.keys()))
        while True:
            processed = await self._process_once()
            if not processed:
                await asyncio.sleep(self.poll_interval_seconds)
