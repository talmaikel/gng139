"""
Entrypoint for the background dossier-generation worker.

Run with:  python -m app.worker
"""

import asyncio
import logging
import uuid
from datetime import datetime

import pymupdf
from sqlalchemy import func, select

from app.cities.herzliya.archive_client import HerzliyaArchiveClient
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.queue import TaskQueueWorker
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity
from app.pipeline.extractor import extract_total_building_area
from app.pipeline.preprocessor import preprocess_blueprint
from app.services.dwelling_units import (
    check_unit_count,
    load_units,
    persist_unit_readings,
    resolve_existing_unit_area,
)
from app.services.economic.assumptions import get_assumptions
from app.services.economic.calculator import calculate_feasibility
from app.services.economic.construction_costs import (
    resolve_construction_cost_per_sqm, resolve_underground_cost_per_sqm,
)
from app.services.economic.schemas import FeasibilityInput
from app.services.market_data.govmap import MarketDataUnavailable
from app.services.market_data.service import get_or_refresh_market_valuation
from app.services.residential_share import location_for as residential_location_for, record_ocr_candidate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("shaked.worker")
settings = get_settings()

# Courtesy caps so one dossier job can't hammer a municipal archive server.
MAX_TIK_IDS = 5
MAX_DOCUMENTS_PER_TIK = 3


async def _fetch_permit_pdfs(opportunity: Opportunity) -> list[tuple[bytes, dict]]:
    """
    Real municipal-archive lookup for cities with a wired client. Herzliya's
    archive is a plain HTTP API (see archive_client.py) rather than a
    JS-rendered page, so no browser automation is needed here. Returns each
    document's raw PDF bytes together with its source record (URL, retrieval
    time, SHA-256).

    The source record travels with the bytes because anything extracted from
    a document has to be able to name where it came from -- a dwelling-unit
    row without a source URL and a retrieval time cannot be checked by
    anyone, and the repo's own contribution rule forbids adding one.
    """
    if opportunity.city_code != "herzliya" or not opportunity.block or not opportunity.parcel:
        return []

    async with HerzliyaArchiveClient() as client:
        tik_ids = await client.find_tik_ids(opportunity.block, opportunity.parcel)
        documents_with_source = []
        for tik_id in tik_ids[:MAX_TIK_IDS]:
            documents = await client.find_documents(tik_id)
            for document in documents[:MAX_DOCUMENTS_PER_TIK]:
                documents_with_source.append(await client.download_with_source(document))
        return documents_with_source


def _rasterize_pdf(pdf_bytes: bytes, dpi: int = 200) -> list[bytes]:
    """Render every page of a PDF to a PNG image, ready for the OCR pipeline."""
    pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_pixmap(dpi=dpi).tobytes("png") for page in pdf]


async def _existing_area_sqm(session, opportunity_id) -> float | None:
    """The seeded `existing_area` for this parcel (footprint x floors x k).

    Read from evidence rather than recomputed, so the dossier and the seeded
    layer can never quietly disagree about the same number. Returns None when
    the parcel was never seeded with one -- the caller then has no fallback
    denominator, which is reported as such rather than filled in.
    """
    result = await session.execute(
        select(FieldEvidence.value)
        .where(
            FieldEvidence.opportunity_id == opportunity_id,
            FieldEvidence.field == "existing_area",
            FieldEvidence.value.isnot(None),
        )
        .order_by(FieldEvidence.created_at.desc())
        .limit(1)
    )
    value = result.scalar_one_or_none()
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _existing_floors(session, opportunity_id) -> int | None:
    """The seeded existing-building floor count (AGOL `Num_floors`, max over
    the parcel's buildings) -- mirrors `_existing_area_sqm`. This is the
    *existing* building's floors, an independent official reading; it has
    nothing to do with `rights.floors()`, which computes how many *new*
    floors the Shaked policy permits.
    """
    result = await session.execute(
        select(FieldEvidence.value)
        .where(
            FieldEvidence.opportunity_id == opportunity_id,
            FieldEvidence.field == "floors",
            FieldEvidence.value.isnot(None),
        )
        .order_by(FieldEvidence.created_at.desc())
        .limit(1)
    )
    value = result.scalar_one_or_none()
    try:
        return int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _check_floor_count(declared: int | None, known: int | None) -> str | None:
    """Cross-check the permit legend's own declared floor count against the
    existing official reading. Same shape as dwelling_units.check_unit_count
    and the same caution: a note to record, never used to overwrite either
    figure -- agreement is free corroboration, disagreement is a genuine
    finding (an addition since the permit, a misread legend, or the
    official layer being wrong), not something this pipeline may resolve
    on its own.
    """
    if declared is None or known is None or declared == known:
        return None
    return (
        f"Floor-count conflict: the permit legend states {declared} floor(s), "
        f"the existing official reading shows {known}. Both are kept; the gap "
        "may mean the building was altered since the permit, that the legend "
        "was misread, or that the official reading is wrong."
    )


def _average_existing_unit_input(assumptions, unit_area):
    """Resolve the calculator value, its blockers and its audit record.

    The assumptions library intentionally marks its 70 sqm placeholder as
    missing. Once a complete verified schedule replaces that placeholder, the
    old blocker must be removed; otherwise even verified data can never make a
    dossier deliverable. Conversely, when the placeholder is still used, its
    own source/status must be reported rather than attributing it to "none".
    """
    blocking_inputs = [
        name
        for name in assumptions.blocking()
        if name != "average_existing_unit_sqm"
    ]

    if unit_area.average_existing_unit_sqm is None:
        fallback = assumptions.average_existing_unit_sqm
        blocking_inputs.append("average_existing_unit_sqm")
        report = {
            "value": fallback.value,
            "status": fallback.status.value,
            "source": fallback.source,
            "notes": unit_area.notes,
        }
        return fallback.value, blocking_inputs, report

    if not unit_area.may_decide:
        blocking_inputs.append("average_existing_unit_sqm")
    report = {
        "value": unit_area.average_existing_unit_sqm,
        "status": unit_area.certainty.value,
        "source": unit_area.source,
        "notes": unit_area.notes,
    }
    return unit_area.average_existing_unit_sqm, blocking_inputs, report


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


async def _opportunity_centroid(session, opportunity_id: uuid.UUID) -> tuple[float, float]:
    statement = select(
        func.ST_Y(func.ST_Centroid(Opportunity.geom)),
        func.ST_X(func.ST_Centroid(Opportunity.geom)),
    ).where(Opportunity.id == opportunity_id)
    row = (await session.execute(statement)).one()
    return float(row[0]), float(row[1])


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
    developer_construction_cost_per_sqm_ils = payload.get("construction_cost_per_sqm_ils")

    async with AsyncSessionLocal() as session:
        opportunity = await session.get(Opportunity, opportunity_id)
        if opportunity is None:
            raise ValueError(f"Opportunity {opportunity_id} not found")

        dossier: dict = {
            "opportunity_id": str(opportunity_id),
            "address": opportunity.address,
            "city_code": opportunity.city_code,
        }

        # Market transactions are intentionally fetched only here, after an
        # opportunity was selected for a dossier. Layer A remains a cheap,
        # citywide screen; this is the expensive/on-demand final-three step.
        latitude, longitude = await _opportunity_centroid(session, opportunity_id)
        market_result = None
        try:
            market_result = await get_or_refresh_market_valuation(
                session,
                opportunity_id=opportunity_id,
                latitude=latitude,
                longitude=longitude,
                city_code=opportunity.city_code,
                metadata=opportunity.metadata_json,
                radius_m=settings.market_data_radius_m,
                lookback_months=settings.market_data_lookback_months,
                cache_days=settings.market_data_cache_days,
            )
            dossier["market_valuation"] = market_result.valuation.model_dump(mode="json")
            dossier["market_valuation"]["cache_hit"] = market_result.cache_hit
            await session.commit()
        except MarketDataUnavailable as exc:
            # A public upstream with no SLA must not destroy an otherwise
            # useful dossier. The fallback stays explicit and auditable.
            dossier["market_valuation"] = {
                "status": "unavailable",
                "error": str(exc),
                "fallback": "versioned_city_assumption",
            }

        plot_area_sqm = float(opportunity.area_sqm) if opportunity.area_sqm else None

        pdf_documents = await _fetch_permit_pdfs(opportunity)
        dossier["documents_found"] = len(pdf_documents)

        extraction_results = []
        # The best per-apartment schedule seen across every page, with the page
        # it came from and that document's source record. "Best" is simply the
        # longest plausible schedule: a permit file often repeats a partial
        # schedule in a title block, and the fullest reading is the one worth
        # keeping.
        best_schedule: tuple[list, str, str, dict] | None = None
        best_schedule_plausible_count = 0

        # W10 (#115): the first page that states its own residential-area
        # figure against a known, sane total. "First" rather than "best" --
        # unlike the unit schedule, this is a single scalar a legend states
        # once; there is no partial reading to prefer over another.
        best_residential: tuple[float, float, str, str, dict] | None = None

        # First non-null declared count seen for either -- both are single
        # scalars a legend states once (a summary line, not a per-row
        # count), so there is nothing to prefer one reading over another.
        best_declared_unit_count: int | None = None
        best_declared_floor_count: int | None = None

        for document_index, (pdf_bytes, document_source) in enumerate(pdf_documents, start=1):
            for page_index, page_bytes in enumerate(_rasterize_pdf(pdf_bytes), start=1):
                preprocessed = preprocess_blueprint(page_bytes)
                extraction = await extract_total_building_area(preprocessed.legend_crop, page_bytes, plot_area_sqm)
                page_ref = f"document {document_index}, page {page_index}"
                extraction_results.append(
                    {
                        "total_building_area_sqm": extraction.total_building_area_sqm,
                        "confidence": extraction.confidence,
                        "method": extraction.method,
                        "is_plausible": extraction.is_plausible,
                        "plausibility_reason": extraction.plausibility_reason,
                        "requires_human_review": extraction.requires_human_review,
                        "page_ref": page_ref,
                        "source_url": document_source.get("url"),
                        "units_read": len(extraction.units),
                        "declared_unit_count": extraction.declared_unit_count,
                        "units_total_area_sqm": extraction.units_total_area_sqm,
                        "residential_area_sqm": extraction.residential_area_sqm,
                        "declared_floor_count": extraction.declared_floor_count,
                    }
                )
                usable_units = [u for u in extraction.units if u.is_plausible]
                if len(usable_units) > best_schedule_plausible_count:
                    best_schedule = (extraction.units, extraction.method, page_ref, document_source)
                    best_schedule_plausible_count = len(usable_units)

                if best_declared_unit_count is None and extraction.declared_unit_count is not None:
                    best_declared_unit_count = extraction.declared_unit_count
                if best_declared_floor_count is None and extraction.declared_floor_count is not None:
                    best_declared_floor_count = extraction.declared_floor_count

                if (
                    best_residential is None
                    and extraction.residential_area_sqm is not None
                    and extraction.total_building_area_sqm is not None
                    and 0 < extraction.residential_area_sqm <= extraction.total_building_area_sqm
                ):
                    best_residential = (
                        extraction.residential_area_sqm, extraction.total_building_area_sqm,
                        extraction.method, page_ref, document_source,
                    )

        dossier["extraction_results"] = extraction_results

        # Persist the per-apartment detail itself, not just its sum: tenant
        # compensation is allocated per household, and a total cannot be
        # attributed to anyone.
        if best_schedule:
            readings, method, page_ref, document_source = best_schedule
            retrieved_at = document_source.get("retrieved_at")
            await persist_unit_readings(
                session,
                opportunity_id,
                readings,
                method=method,
                document_ref=page_ref,
                source_url=document_source.get("url"),
                retrieved_at=datetime.fromisoformat(retrieved_at) if retrieved_at else None,
            )
            await session.flush()

        # W10 (#115): the §70א 70%-residential gate previously had no open
        # source at all -- a person had to read the gramoshka's area table
        # by hand. When the same table states its own residential figure,
        # write it as a displayed candidate; it still cannot decide the gate
        # on its own (see residential_share.record_ocr_candidate), and it
        # never contests a person's own manually-verified answer.
        if best_residential:
            residential_sqm, total_sqm, method, page_ref, document_source = best_residential
            retrieved_at_raw = document_source.get("retrieved_at")
            await record_ocr_candidate(
                session, opportunity_id,
                residential_sqm=residential_sqm, total_sqm=total_sqm,
                source_url=document_source.get("url"),
                retrieved_at=datetime.fromisoformat(retrieved_at_raw) if retrieved_at_raw else None,
                location=residential_location_for(residential_sqm, total_sqm, page=page_ref),
                method=method,
            )

        stored_units = await load_units(session, opportunity_id)
        dossier["dwelling_units"] = [
            {
                "unit_label": u.unit_label,
                "floor": u.floor,
                "area_sqm": u.area_sqm,
                "certainty": u.certainty.value,
                "requires_human_review": u.requires_human_review,
                "method": u.method,
                "location": u.location,
                "source_url": u.source_url,
                "retrieved_at": u.retrieved_at.isoformat() if u.retrieved_at else None,
            }
            for u in stored_units
        ]

        buildable_area_sqm, buildable_area_source = _select_buildable_area(extraction_results, plot_area_sqm)
        dossier["buildable_area_source"] = buildable_area_source

        # `existing_area` (footprint x floors x k) is the fallback denominator
        # for a uniform average when no schedule was read. It is an ESTIMATE by
        # construction -- k was calibrated against a single permit -- so it can
        # only ever produce another ESTIMATE.
        existing_area_sqm = await _existing_area_sqm(session, opportunity_id)

        # Every number the gramoshka's legend states about the building,
        # cross-checked against what was already known -- never used to
        # overwrite either side. Displayed unconditionally (empty when there
        # is nothing to compare) rather than only appearing on disagreement,
        # so its absence cannot be mistaken for "no permit was read."
        existing_floors = await _existing_floors(session, opportunity_id)
        dossier["gramoshka_cross_checks"] = [
            note for note in (
                check_unit_count(best_declared_unit_count, opportunity.existing_units),
                _check_floor_count(best_declared_floor_count, existing_floors),
            ) if note
        ]

        unit_area = resolve_existing_unit_area(
            stored_units,
            municipal_unit_count=opportunity.existing_units,
            existing_area_sqm=existing_area_sqm,
        )
        dossier["existing_unit_area"] = {
            "average_existing_unit_sqm": unit_area.average_existing_unit_sqm,
            "source": unit_area.source,
            "certainty": unit_area.certainty.value,
            "per_unit_detail_available": unit_area.per_unit_detail_available,
            "unit_count": unit_area.unit_count,
            "may_decide": unit_area.may_decide,
            "schedule_complete": unit_area.schedule_complete,
            "has_unit_count_conflict": unit_area.has_unit_count_conflict,
            "notes": unit_area.notes,
        }
        # Allocating compensation per household on a building-wide average
        # short-changes whoever is below it. Stated as a capability of this
        # dossier rather than left for a caller to infer.
        dossier["per_household_compensation_supported"] = unit_area.per_unit_detail_available

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
            market_price = (
                market_result.valuation.blended_price_per_sqm_ils
                if market_result and market_result.valuation.is_unit_mix_adjusted
                else None
            )
            sale_price_per_sqm = market_price or assumptions.sale_price_per_sqm_ils.value

            # Prefer this building's own average over the city-wide assumption.
            # When it cannot decide (unreviewed OCR, or a footprint estimate),
            # it still feeds the scenario -- a scenario on a placeholder is
            # useful to reason with -- but joins `missing_inputs`, so the
            # result comes back is_deliverable=False rather than looking like
            # it rested on data.
            (
                average_existing_unit_sqm,
                blocking_inputs,
                average_existing_unit_report,
            ) = _average_existing_unit_input(assumptions, unit_area)

            # B2: the developer's own figure, then the appraisers' regional
            # survey, decide this before the versioned per-city assumption
            # ever gets a say -- see construction_costs.py. This pipeline has
            # no rights assessment to read a floor count from (unlike
            # dossier.py), so it always averages the survey's three height
            # bands rather than picking one.
            construction_cost = resolve_construction_cost_per_sqm(
                opportunity.city_code, developer_construction_cost_per_sqm_ils
            )
            blocking_inputs = [name for name in blocking_inputs if name != "construction_cost_per_sqm_ils"]
            if construction_cost.value_ils_per_sqm is None:
                blocking_inputs.append("construction_cost_per_sqm_ils")
                construction_cost_per_sqm = assumptions.construction_cost_per_sqm_ils.value
            else:
                construction_cost_per_sqm = construction_cost.value_ils_per_sqm

            underground_cost = resolve_underground_cost_per_sqm(opportunity.city_code)
            underground_cost_per_sqm = (underground_cost.value_ils_per_sqm
                                        or assumptions.underground_cost_per_sqm_ils.value)

            feasibility = calculate_feasibility(
                FeasibilityInput(
                    plot_area_sqm=plot_area_sqm,
                    existing_units=opportunity.existing_units,
                    buildable_area_sqm=buildable_area_sqm,
                    sale_price_per_sqm=sale_price_per_sqm,
                    construction_cost_per_sqm=construction_cost_per_sqm,
                    soft_cost_ratio=assumptions.soft_cost_ratio.value,
                    demolition_cost_per_unit=assumptions.demolition_cost_per_unit_ils.value,
                    developer_profit_target_ratio=assumptions.developer_profit_target_ratio.value,
                    # Was never passed, so every dossier silently used the
                    # schema default of 70 sqm -- the largest single deduction
                    # from the developer's share, undeclared and unreported.
                    # Now this building's own figure where one exists, with the
                    # city assumption only as a last resort.
                    average_existing_unit_sqm=average_existing_unit_sqm,
                    tenant_compensation_sqm_per_existing_unit=(
                        assumptions.tenant_compensation_sqm_per_existing_unit.value),
                    main_area_ratio=assumptions.main_area_ratio.value,
                    underground_ratio=assumptions.underground_ratio.value,
                    underground_cost_per_sqm=underground_cost_per_sqm,
                    tenant_rent_months=assumptions.tenant_rent_months.value,
                    tenant_monthly_rent_ils=assumptions.tenant_monthly_rent_ils.value,
                    tenant_moving_cost_ils=assumptions.tenant_moving_cost_ils.value,
                    tenant_legal_cost_per_unit_ils=assumptions.tenant_legal_cost_per_unit_ils.value,
                    marketing_ratio=assumptions.marketing_ratio.value,
                    guarantees_ratio=assumptions.guarantees_ratio.value,
                    finance_ratio=assumptions.finance_ratio.value,
                    betterment_levy_rate=assumptions.betterment_levy_rate.value,
                    betterment_base_ils=assumptions.betterment_base_ils.value,
                    vat_rate=assumptions.vat_rate.value,
                ),
                missing_inputs=blocking_inputs,
            )
            dossier["feasibility"] = feasibility.model_dump()
            # Per PRD ECO-02, every commercial component is marked data /
            # estimate / missing, and the assumptions library carries a date
            # and version -- surfaced here rather than left implicit.
            # Generated from the assumption set rather than hand-listed: the
            # hand-written version omitted developer_profit_target_ratio and
            # average_existing_unit_sqm, and nothing noticed.
            dossier["feasibility_assumptions"] = {
                "assumptions_version": assumptions.version,
                "assumptions_effective_date": assumptions.effective_date.isoformat(),
                **assumptions.report(),
                # Overrides the placeholder entry from assumptions.report():
                # this dossier's actual figure came from the developer or the
                # appraisers' survey, resolved above, not the versioned
                # per-city assumption.
                "construction_cost_per_sqm_ils": {
                    "value": construction_cost_per_sqm,
                    "status": construction_cost.status,
                    "unit": "ILS/sqm",
                    "source": construction_cost.source,
                    "method": construction_cost.method,
                    "as_of_date": (
                        construction_cost.as_of_date.isoformat() if construction_cost.as_of_date else None
                    ),
                },
                "underground_cost_per_sqm_ils": {
                    "value": underground_cost_per_sqm,
                    "status": underground_cost.status,
                    "unit": "ILS/sqm",
                    "source": underground_cost.source,
                    "method": underground_cost.method,
                },
                "sale_price_per_sqm_ils": {
                    "value": sale_price_per_sqm,
                    "status": "estimate",
                    "unit": "ILS/sqm",
                    "source": (
                        market_result.valuation.source_url
                        if market_price and market_result
                        else assumptions.sale_price_per_sqm_ils.source
                    ),
                    "as_of_date": (
                        market_result.valuation.as_of_date.isoformat()
                        if market_price and market_result
                        else assumptions.effective_date.isoformat()
                    ),
                    "method": (
                        "local_comparable_sales_weighted_by_explicit_unit_mix"
                        if market_price
                        else "versioned_city_fallback_no_explicit_unit_mix"
                    ),
                },
                # Overrides the city-wide entry printed by report(): when this
                # building's own schedule was used, the report must not still
                # claim the scenario rested on the generic assumption.
                "average_existing_unit_sqm": average_existing_unit_report,
            }

        # True whenever a human needs to confirm a figure before this dossier
        # is relied on: an unverified AI-derived buildable area, or any
        # extraction attempt that failed the bounds check outright.
        dossier["requires_human_review"] = (
            buildable_area_source == "ai_assisted_unverified"
            or any(not r["is_plausible"] for r in extraction_results)
            # A schedule was read but nobody has confirmed it yet: the areas
            # are in the dossier and must not be acted on until they are.
            or any(u.requires_human_review for u in stored_units)
        )

        # This handler now writes (dwelling_units); it used to be read-only.
        await session.commit()

    return dossier


async def main() -> None:
    worker = TaskQueueWorker()
    worker.register("generate_dossier", generate_dossier_handler)
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
