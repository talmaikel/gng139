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
from app.services.economic.assumptions import get_assumptions
from app.services.economic.calculator import calculate_feasibility
from app.services.economic.schemas import FeasibilityInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shaked.worker")

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


def _select_buildable_area(extraction_results: list[dict], plot_area_sqm: float | None) -> tuple[float | None, str]:
    """
    Never treat an AI-fallback figure as verified fact, even when it passes
    the bounds check (extractor.py has observed gpt-4o-mini confidently
    misread a plot number as a building area -- a plausible-looking number
    the bounds check can't catch). Local OCR matches that pass the bounds
    check are the only ones trusted for the calculator; an AI-derived one is
    used only as a last resort, always flagged for review.

    Per the Shaked PRD (6.4): "if there is no sufficient planning basis for
    the scenario, the system does not invent rights" -- so when nothing
    usable was extracted, this returns None rather than a guessed figure
    (e.g. a fraction of the plot area), and the caller must not compute a
    feasibility scenario at all.
    """
    trusted_local = [
        r for r in extraction_results
        if r["is_plausible"] and not r["requires_human_review"] and r["total_building_area_sqm"]
    ]
    reviewable_ai = [
        r for r in extraction_results
        if r["is_plausible"] and r["requires_human_review"] and r["total_building_area_sqm"]
    ]

    if trusted_local:
        return max(r["total_building_area_sqm"] for r in trusted_local), "local_ocr"
    if reviewable_ai:
        return max(r["total_building_area_sqm"] for r in reviewable_ai), "ai_assisted_unverified"
    return None, "insufficient_planning_basis"


async def generate_dossier_handler(payload: dict) -> dict:
    """
    Assemble a dossier for one opportunity: pull real municipal archive
    documents (where a scraper is wired for the city), OCR-extract the total
    building area from each page, and run the economic feasibility
    calculator -- but only when every input the PRD treats as a required
    "property input" (plot area, existing units, buildable area) is a real,
    substantiated value. Per PRD 6.4, this handler never invents one of
    those and presents the dossier as ready; a missing input blocks the
    scenario instead.

    A genuine failure anywhere in this chain (archive unreachable, OCR
    confidence too low with no AI fallback configured, unknown city in the
    assumptions library, etc.) propagates to the caller, where
    TaskQueueWorker persists it as a 'failed' task with the error message --
    this is the queue's designed failure path, not something this handler
    should swallow.
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

        plot_area_sqm = float(opportunity.area_sqm) if opportunity.area_sqm else None

        pdf_documents = await _fetch_permit_pdfs(opportunity)
        dossier["documents_found"] = len(pdf_documents)

        extraction_results = []
        for pdf_bytes in pdf_documents:
            for page_bytes in _rasterize_pdf(pdf_bytes):
                preprocessed = preprocess_blueprint(page_bytes)
                extraction = await extract_total_building_area(preprocessed.legend_crop, page_bytes, plot_area_sqm)
                extraction_results.append(
                    {
                        "total_building_area_sqm": extraction.total_building_area_sqm,
                        "confidence": extraction.confidence,
                        "method": extraction.method,
                        "is_plausible": extraction.is_plausible,
                        "plausibility_reason": extraction.plausibility_reason,
                        "requires_human_review": extraction.requires_human_review,
                    }
                )
        dossier["extraction_results"] = extraction_results

        buildable_area_sqm, buildable_area_source = _select_buildable_area(extraction_results, plot_area_sqm)
        dossier["buildable_area_source"] = buildable_area_source

        missing_property_inputs = [
            name
            for name, value in (
                ("plot_area_sqm", plot_area_sqm),
                ("existing_units", opportunity.existing_units),
                ("buildable_area_sqm", buildable_area_sqm),
            )
            if value is None
        ]

        if missing_property_inputs:
            dossier["feasibility"] = None
            dossier["feasibility_assumptions"] = None
            dossier["scenario_note"] = (
                "No economic scenario computed -- missing required property input(s): "
                f"{', '.join(missing_property_inputs)}. Per the Shaked PRD (6.4), the system "
                "does not invent rights or present an estimated figure as a verified one when "
                "there is no sufficient planning basis."
            )
        else:
            assumptions = get_assumptions(opportunity.city_code)
            feasibility = calculate_feasibility(
                FeasibilityInput(
                    plot_area_sqm=plot_area_sqm,
                    existing_units=opportunity.existing_units,
                    buildable_area_sqm=buildable_area_sqm,
                    sale_price_per_sqm=assumptions.sale_price_per_sqm_ils.value,
                    construction_cost_per_sqm=assumptions.construction_cost_per_sqm_ils.value,
                    soft_cost_ratio=assumptions.soft_cost_ratio.value,
                    demolition_cost_per_unit=assumptions.demolition_cost_per_unit_ils.value,
                    developer_profit_target_ratio=assumptions.developer_profit_target_ratio.value,
                )
            )
            dossier["feasibility"] = feasibility.model_dump()
            # Per PRD ECO-02, every commercial component is marked data /
            # estimate / missing, and the assumptions library carries a date
            # and version -- surfaced here rather than left implicit.
            dossier["feasibility_assumptions"] = {
                "assumptions_version": assumptions.version,
                "assumptions_effective_date": assumptions.effective_date.isoformat(),
                "sale_price_per_sqm_ils": {
                    "value": assumptions.sale_price_per_sqm_ils.value,
                    "status": assumptions.sale_price_per_sqm_ils.status.value,
                },
                "construction_cost_per_sqm_ils": {
                    "value": assumptions.construction_cost_per_sqm_ils.value,
                    "status": assumptions.construction_cost_per_sqm_ils.status.value,
                },
                "soft_cost_ratio": {
                    "value": assumptions.soft_cost_ratio.value,
                    "status": assumptions.soft_cost_ratio.status.value,
                },
                "demolition_cost_per_unit_ils": {
                    "value": assumptions.demolition_cost_per_unit_ils.value,
                    "status": assumptions.demolition_cost_per_unit_ils.status.value,
                },
            }

        # True whenever a human needs to confirm a figure before this dossier
        # is relied on: an unverified AI-derived buildable area, or any
        # extraction attempt that failed the bounds check outright.
        dossier["requires_human_review"] = buildable_area_source == "ai_assisted_unverified" or any(
            not r["is_plausible"] for r in extraction_results
        )

    return dossier


async def main() -> None:
    worker = TaskQueueWorker()
    worker.register("generate_dossier", generate_dossier_handler)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
