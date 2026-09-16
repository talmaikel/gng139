import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("shaked.main")


async def _run_worker_forever() -> None:
    # Imported lazily: the worker pulls in OCR/CV modules the API alone does not need.
    from app.worker import generate_dossier_handler
    from app.core.queue import TaskQueueWorker

    worker = TaskQueueWorker()
    worker.register("generate_dossier", generate_dossier_handler)
    while True:
        try:
            await worker.run_forever()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a DB hiccup must not stop jobs until the next deploy
            logger.exception("In-process worker crashed; restarting in 10s")
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Render's free plan has no background workers, so the deployment runs the
    # queue worker inside the API process. Locally, run `python -m app.worker`.
    task = None
    if os.getenv("RUN_WORKER_IN_PROCESS", "").lower() in {"1", "true", "yes"}:
        task = asyncio.create_task(_run_worker_forever())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    lifespan=lifespan,
    title="Shaked Engine API",
    description="B2B urban-renewal opportunity screening under the Shaked Alternative (חלופת שקד).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
