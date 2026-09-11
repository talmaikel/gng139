"""
Entrypoint for the background dossier-generation worker.

Run with:  python -m app.worker
"""

import asyncio
import logging

from app.core.queue import TaskQueueWorker

logging.basicConfig(level=logging.INFO)


async def generate_dossier_handler(payload: dict) -> dict:
    """
    Placeholder dossier-generation job: wire this up to the pipeline
    (scraper -> preprocessor -> extractor) and the economic calculator
    once the end-to-end dossier assembly is implemented.
    """
    opportunity_id = payload["opportunity_id"]
    return {"opportunity_id": opportunity_id, "dossier": "not_yet_implemented"}


async def main() -> None:
    worker = TaskQueueWorker()
    worker.register("generate_dossier", generate_dossier_handler)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
