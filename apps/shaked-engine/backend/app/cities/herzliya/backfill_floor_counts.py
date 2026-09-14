"""Batch the 39 B6 parcels through B3's permit-sheet floor-count extraction.

This does NOT fill ``Opportunity.existing_units``. B6 is the dwelling-unit-count
work item; a building floor count is useful supporting data but cannot safely be
converted into a unit count.

Run from ``apps/shaked-engine/backend``::

    python -m app.cities.herzliya.backfill_floor_counts

The command selects Herzliya opportunities whose ``existing_units`` is NULL,
scans their permit sheets with the same B3 pipeline used by dossiers, and writes
an auditable CSV under ``POC/layer_a/validation/``. Rows that have no explicit
whole-building count, or have conflicting permit-sheet counts, are marked for
manual D review in Google Maps/Street View.
"""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.opportunity import Opportunity
from app.pipeline.extractor import extract_total_building_area
from app.pipeline.preprocessor import preprocess_blueprint
from app.worker import _fetch_permit_pdfs, _rasterize_pdf, _select_observed_floor_count

OUTPUT = Path("POC/layer_a/validation/b6_floor_counts.csv")


@dataclass
class FloorCountRow:
    opportunity_id: str
    address: str
    block: str | None
    parcel: str | None
    floor_count: int | None
    status: str
    source_url: str | None
    page_ref: str | None
    method: str | None
    confidence: float | None
    manual_d_review: bool
    manual_d_reason: str | None


async def _scan_one(opportunity: Opportunity) -> FloorCountRow:
    extraction_results: list[dict] = []
    plot_area_sqm = float(opportunity.area_sqm) if opportunity.area_sqm else None

    try:
        pdf_documents = await _fetch_permit_pdfs(opportunity)
    except Exception as exc:  # keep one archive failure from aborting the batch
        return FloorCountRow(
            opportunity_id=str(opportunity.id),
            address=opportunity.address,
            block=opportunity.block,
            parcel=opportunity.parcel,
            floor_count=None,
            status="archive_error",
            source_url=None,
            page_ref=None,
            method=None,
            confidence=None,
            manual_d_review=True,
            manual_d_reason=f"archive_error: {type(exc).__name__}: {exc}",
        )

    for document_index, (pdf_bytes, document_source) in enumerate(pdf_documents, start=1):
        for page_index, page_bytes in enumerate(_rasterize_pdf(pdf_bytes), start=1):
            try:
                preprocessed = preprocess_blueprint(page_bytes)
                extraction = await extract_total_building_area(
                    preprocessed.legend_crop, page_bytes, plot_area_sqm
                )
            except Exception:
                # Another page/document may still carry the explicit count.
                continue
            extraction_results.append(
                {
                    "declared_floor_count": extraction.declared_floor_count,
                    "confidence": extraction.confidence,
                    "method": extraction.method,
                    "page_ref": f"document {document_index}, page {page_index}",
                    "source_url": document_source.get("url"),
                }
            )

    observed = _select_observed_floor_count(extraction_results)
    status = str(observed["status"])
    needs_manual = status != "observed_unverified"
    if status == "missing":
        reason = "לא נמצא מספר קומות מפורש בגרמושקות שנסרקו"
    elif status == "conflict":
        reason = "נמצאו מספרי קומות סותרים בין מסמכים"
    else:
        reason = None

    return FloorCountRow(
        opportunity_id=str(opportunity.id),
        address=opportunity.address,
        block=opportunity.block,
        parcel=opportunity.parcel,
        floor_count=observed.get("value"),
        status=status,
        source_url=observed.get("source_url"),
        page_ref=observed.get("page_ref"),
        method=observed.get("method"),
        confidence=observed.get("confidence"),
        manual_d_review=needs_manual,
        manual_d_reason=reason,
    )


def _write(rows: list[FloorCountRow]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FloorCountRow.__annotations__))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


async def run() -> list[FloorCountRow]:
    async with AsyncSessionLocal() as session:
        opportunities = list(
            (
                await session.execute(
                    select(Opportunity)
                    .where(
                        Opportunity.city_code == "herzliya",
                        Opportunity.existing_units.is_(None),
                    )
                    .order_by(Opportunity.address, Opportunity.block, Opportunity.parcel)
                )
            ).scalars()
        )

    rows: list[FloorCountRow] = []
    for opportunity in opportunities:
        rows.append(await _scan_one(opportunity))

    _write(rows)
    automatic = sum(1 for row in rows if not row.manual_d_review)
    manual = len(rows) - automatic
    print(
        f"B6 parcel set: {len(rows)} | floor count from B3: {automatic} | "
        f"manual D review: {manual} | output: {OUTPUT}"
    )
    return rows


if __name__ == "__main__":
    asyncio.run(run())
