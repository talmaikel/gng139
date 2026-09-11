"""
Entrypoint for the background dossier-generation worker.

Run with:  python -m app.worker
"""

import asyncio
import logging
import uuid

import pymupdf

from app.cities.herzliya.archive_client import HerzliyaArchiveClient
from app.core.database import AsyncSessionLocal
from app.core.queue import TaskQueueWorker
from app.models.opportunity import Opportunity
from app.pipeline.extractor import extract_total_building_area
from app.pipeline.preprocessor import preprocess_blueprint
from app.services.economic.calculator import calculate_feasibility
from app.services.economic.schemas import FeasibilityInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shaked.worker")

# Placeholder market assumptions used until per-city/per-opportunity figures
# are available from a real source. See PRODUCT_STRUCTURE.md known gaps.
DEFAULT_SALE_PRICE_PER_SQM_ILS = 45_000.0
DEFAULT_CONSTRUCTION_COST_PER_SQM_ILS = 8_000.0
DEFAULT_EXISTING_UNITS = 1
DEFAULT_PLOT_AREA_SQM = 600.0

# Courtesy caps so one dossier job can't hammer a municipal archive server.
MAX_TIK_IDS = 5
MAX_DOCUMENTS_PER_TIK = 3


async def _fetch_permit_pdfs(opportunity: Opportunity) -> list[bytes]:
    """
    Real municipal-archive lookup for cities with a wired client. Herzliya's
    archive is a plain HTTP API (see archive_client.py) rather than a
    JS-rendered page, so no browser automation is needed here. Returns raw
    PDF bytes for every attached document found.
    """
    if opportunity.city_code != "herzliya" or not opportunity.block or not opportunity.parcel:
        return []

    async with HerzliyaArchiveClient() as client:
        tik_ids = await client.find_tik_ids(opportunity.block, opportunity.parcel)
        pdf_bytes_list = []
        for tik_id in tik_ids[:MAX_TIK_IDS]:
            documents = await client.find_documents(tik_id)
            for document in documents[:MAX_DOCUMENTS_PER_TIK]:
                pdf_bytes_list.append(await client.download(document))
        return pdf_bytes_list


def _rasterize_pdf(pdf_bytes: bytes, dpi: int = 200) -> list[bytes]:
    """Render every page of a PDF to a PNG image, ready for the OCR pipeline."""
    pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_pixmap(dpi=dpi).tobytes("png") for page in pdf]


async def generate_dossier_handler(payload: dict) -> dict:
    """
    Assemble a dossier for one opportunity: pull real municipal archive
    documents (where a scraper is wired for the city), OCR-extract the total
    building area from each page, and run the economic feasibility
    calculator against the best figure found.

    A genuine failure anywhere in this chain (archive unreachable, OCR
    confidence too low with no AI fallback configured, etc.) propagates to
    the caller, where TaskQueueWorker persists it as a 'failed' task with
    the error message -- this is the queue's designed failure path, not
    something this handler should swallow.
    """
    opportunity_id = uuid.UUID(payload["opportunity_id"])

    async with AsyncSessionLocal() as session:
        opportunity = await session.get(Opportunity, opportunity_id)
        if opportunity is None:
            raise ValueError(f"Opportunity {opportunity_id} not found")

        dossier: dict = {
            "opportunity_id": str(opportunity_id),
            "address": opportunity.address,
            "city_code": opportunity.city_code,
        }

        pdf_documents = await _fetch_permit_pdfs(opportunity)
        dossier["documents_found"] = len(pdf_documents)

        extraction_results = []
        for pdf_bytes in pdf_documents:
            for page_bytes in _rasterize_pdf(pdf_bytes):
                preprocessed = preprocess_blueprint(page_bytes)
                extraction = await extract_total_building_area(preprocessed.legend_crop, page_bytes)
                extraction_results.append(
                    {
                        "total_building_area_sqm": extraction.total_building_area_sqm,
                        "confidence": extraction.confidence,
                        "method": extraction.method,
                    }
                )
        dossier["extraction_results"] = extraction_results

        confident_areas = [
            r["total_building_area_sqm"] for r in extraction_results if r["total_building_area_sqm"]
        ]
        plot_area_sqm = float(opportunity.area_sqm) if opportunity.area_sqm else DEFAULT_PLOT_AREA_SQM
        buildable_area_sqm = max(confident_areas) if confident_areas else plot_area_sqm * 0.6

        feasibility = calculate_feasibility(
            FeasibilityInput(
                plot_area_sqm=plot_area_sqm,
                existing_units=DEFAULT_EXISTING_UNITS,
                buildable_area_sqm=buildable_area_sqm,
                sale_price_per_sqm=DEFAULT_SALE_PRICE_PER_SQM_ILS,
                construction_cost_per_sqm=DEFAULT_CONSTRUCTION_COST_PER_SQM_ILS,
            )
        )
        dossier["feasibility"] = feasibility.model_dump()
        dossier["feasibility_assumptions"] = {
            "note": "Placeholder market assumptions, not sourced per-opportunity yet -- see PRODUCT_STRUCTURE.md",
            "buildable_area_source": "ocr" if confident_areas else "estimated_from_plot_area",
            "sale_price_per_sqm_ils": DEFAULT_SALE_PRICE_PER_SQM_ILS,
            "construction_cost_per_sqm_ils": DEFAULT_CONSTRUCTION_COST_PER_SQM_ILS,
            "existing_units_assumed": DEFAULT_EXISTING_UNITS,
        }

    return dossier


async def main() -> None:
    worker = TaskQueueWorker()
    worker.register("generate_dossier", generate_dossier_handler)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
