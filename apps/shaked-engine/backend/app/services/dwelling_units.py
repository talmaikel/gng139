"""
Persisting per-apartment areas, and deciding what the economic calculator is
allowed to do with them.

Two separate jobs, kept apart on purpose:

* `persist_unit_readings` writes what was read, exactly as read, including
  rows that failed the bounds check. It never decides anything.
* `resolve_existing_unit_area` answers one narrow question -- what
  `average_existing_unit_sqm` should the feasibility scenario use, and how far
  is that figure allowed to travel? A verified schedule may decide; a
  footprint average may only be displayed.

The distinction matters because the same number feeds two very different
uses. For *total* developer profit an average is tolerable: an error on a
small apartment nets off against a large one. For *per-household*
compensation nothing nets off -- a tenant whose 55 sqm flat is compensated as
though it were the 78 sqm building average is personally short-changed. So
`resolve_existing_unit_area` reports `per_unit_detail_available`, and callers
that allocate per household must refuse to proceed without it.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evidence import DECIDING, Certainty
from app.models.dwelling_unit import DwellingUnit
from app.pipeline.extractor import DwellingUnitReading
from app.services.economic.existing_area_assumptions import (
    D5_EXISTING_PRIVATE_AREA_RATIO,
)

# How far the permit-sheet unit count may differ from the municipal address
# layer before the dossier calls it a conflict. Kept at zero: these two
# sources answer slightly different questions (what was permitted vs. what is
# registered today), so any gap is a real finding about the building, not
# noise to be tuned away.
UNIT_COUNT_TOLERANCE = 0

# Compatibility name for existing callers/tests. The value itself lives in a
# sourced, dated D5 assumption object rather than as a magic number here.
FOOTPRINT_EXISTING_MAIN_AREA_RATIO = D5_EXISTING_PRIVATE_AREA_RATIO.value


@dataclass
class UnitAreaResolution:
    """What the calculator may use, and what the dossier must say about it."""

    average_existing_unit_sqm: float | None
    source: str                      # "verified_schedule" | "unverified_schedule" | "footprint_average" | "none"
    certainty: Certainty
    # True only when every unit has its own confirmed area. Per-household
    # compensation may not be computed without this.
    per_unit_detail_available: bool
    unit_count: int | None
    notes: list[str]
    # True only when the schedule covers the municipality's known unit count.
    # A verified partial schedule, or a schedule with no independent count to
    # compare against, must not drive a deliverable calculation.
    schedule_complete: bool = False
    # Set when the schedule and the municipal address layer disagree on how
    # many units the building has. A confirmed schedule covering 1 of 28
    # apartments is confirmed for what it read and says nothing about the
    # other 27, so the disagreement has to block the average from deciding
    # rather than merely annotate it.
    has_unit_count_conflict: bool = False
    # Aggregate fallback detail for buildings with no per-unit schedule.
    # These fields are estimates only and must never be mistaken for an
    # as-built or per-household measurement.
    estimated_main_area_sqm: float | None = None
    estimated_common_service_area_sqm: float | None = None
    estimated_main_area_ratio: float | None = None
    estimated_main_area_ratio_source: str | None = None
    estimated_main_area_ratio_status: str | None = None

    @property
    def may_decide(self) -> bool:
        """Whether this figure is allowed to drive a deliverable scenario."""
        return (
            self.certainty.value in DECIDING
            and self.average_existing_unit_sqm is not None
            and self.schedule_complete
            and not self.has_unit_count_conflict
        )


def _certainty_for(method: str | None, is_plausible: bool) -> Certainty:
    """OCR and model readings are candidates until a person confirms them.

    Neither `ocr_candidate` nor `ai_candidate` is in `DECIDING`, so nothing
    written here can decide a scenario on its own -- which is the point.
    """
    if not is_plausible:
        return Certainty.MISSING
    if method == "openai_gpt4o_mini":
        return Certainty.AI_CANDIDATE
    return Certainty.OCR_CANDIDATE


async def persist_unit_readings(
    session: AsyncSession,
    opportunity_id,
    readings: Sequence[DwellingUnitReading],
    *,
    method: str,
    source_url: str | None = None,
    retrieved_at: datetime | None = None,
    document_ref: str = "document",
    building_id=None,
    replace_existing: bool = True,
) -> list[DwellingUnit]:
    """Write one row per apartment read off one document.

    `replace_existing` clears only rows previously written by *this* pipeline
    for this opportunity (any row still awaiting review). Rows a person has
    confirmed are left alone: a re-run of the extractor must not silently
    discard human work, which is the one thing in this table that cannot be
    regenerated.
    """
    if replace_existing:
        await session.execute(
            delete(DwellingUnit).where(
                DwellingUnit.opportunity_id == opportunity_id,
                DwellingUnit.requires_human_review.is_(True),
            )
        )

    confirmed = set(
        (
            await session.execute(
                select(DwellingUnit.source_key).where(
                    DwellingUnit.opportunity_id == opportunity_id,
                    DwellingUnit.requires_human_review.is_(False),
                )
            )
        ).scalars()
    )

    rows: list[DwellingUnit] = []
    for index, reading in enumerate(readings, start=1):
        # Ordinal position is part of the key so an unlabelled row ("the
        # seventh row in the schedule") is still addressable and stable.
        source_key = f"{document_ref}#{reading.unit_label or f'row{index}'}"
        if source_key in confirmed:
            continue  # a person already settled this unit; leave their row in place
        row = DwellingUnit(
            opportunity_id=opportunity_id,
            building_id=building_id,
            source_key=source_key,
            unit_label=reading.unit_label,
            floor=reading.floor,
            area_sqm=reading.area_sqm if reading.is_plausible else None,
            certainty=_certainty_for(method, reading.is_plausible),
            requires_human_review=True,
            source_url=source_url,
            retrieved_at=retrieved_at,
            location=f"{document_ref} · {reading.raw_text}" if reading.raw_text else document_ref,
            method=method,
            raw_text=reading.raw_text,
        )
        session.add(row)
        rows.append(row)

    return rows


async def load_units(session: AsyncSession, opportunity_id) -> list[DwellingUnit]:
    result = await session.execute(
        select(DwellingUnit)
        .where(DwellingUnit.opportunity_id == opportunity_id)
        .order_by(DwellingUnit.unit_label, DwellingUnit.source_key)
    )
    return list(result.scalars())


def check_unit_count(
    schedule_count: int | None, municipal_count: int | None
) -> str | None:
    """Cross-check the permit schedule against the municipal address layer.

    Free, and the single most useful sanity check available here: the two
    sources are independent, so agreement is real corroboration and
    disagreement is a genuine finding -- a permit that was never built as
    drawn, units split since, or a misread schedule. Returned as a note to
    record, never used to overwrite either figure.
    """
    if schedule_count is None or municipal_count is None:
        return None
    if abs(schedule_count - municipal_count) <= UNIT_COUNT_TOLERANCE:
        return None
    return (
        f"Unit-count conflict: the permit schedule shows {schedule_count} unit(s), "
        f"the municipal address layer shows {municipal_count}. Both are kept; the gap "
        "may mean the building was not built as drawn, was re-partitioned since, or "
        "that the schedule was misread."
    )


def resolve_existing_unit_area(
    units: Iterable[DwellingUnit],
    *,
    municipal_unit_count: int | None,
    existing_area_sqm: float | None,
    existing_private_area_ratio: float | None = None,
    existing_private_area_ratio_source: str | None = None,
) -> UnitAreaResolution:
    """Decide the average existing unit area, and how far it may be trusted.

    Order of preference:

    1. A schedule where every unit has been confirmed by a person. Decides,
       and carries per-unit detail, so per-household compensation is possible.
    2. A schedule still awaiting review. Displayed, never decides -- so a
       dossier cannot quietly rest on an unreviewed OCR reading.
    3. When no schedule exists, split the footprint-derived `existing_area`
       using a sourced ESTIMATE from D5. A caller may override that ratio for
       sensitivity/developer input, but the result stays ESTIMATE and never
       decides by itself. `existing_area` is already `footprint x floors x k`;
       until the target-area definition of k is fully reconstructed this
       second split must be presented as an explicit assumption, not DATA.
    """
    notes: list[str] = []
    units = list(units)
    with_area = [u for u in units if u.area_sqm is not None]

    if with_area:
        verified = [u for u in with_area if not u.requires_human_review and u.certainty.value in DECIDING]
        if verified and len(verified) == len(units):
            average = round(sum(u.area_sqm for u in verified) / len(verified), 2)
            notes.append(
                f"Average taken from {len(verified)} confirmed unit area(s) totalling "
                f"{round(sum(u.area_sqm for u in verified), 2)} sqm."
            )
            conflict = check_unit_count(len(verified), municipal_unit_count)
            schedule_complete = (
                municipal_unit_count is not None
                and len(verified) == municipal_unit_count
                and conflict is None
            )
            if conflict:
                notes.append(conflict)
            elif municipal_unit_count is None:
                notes.append(
                    "The schedule is confirmed, but no independent municipal unit count "
                    "is available to prove that it covers the whole building."
                )
            return UnitAreaResolution(
                average_existing_unit_sqm=average,
                source="verified_schedule",
                certainty=Certainty.MANUALLY_VERIFIED,
                # Only a schedule that covers the whole building can support
                # per-household allocation: confirmed areas for 1 of 28
                # apartments leave 27 households with no figure of their own.
                per_unit_detail_available=schedule_complete,
                unit_count=len(verified),
                notes=notes,
                schedule_complete=schedule_complete,
                has_unit_count_conflict=conflict is not None,
            )

        average = round(sum(u.area_sqm for u in with_area) / len(with_area), 2)
        notes.append(
            f"{len(with_area)} unit area(s) were read from the permit sheet but are "
            "not yet confirmed by a person, so they are displayed and cannot drive a "
            "deliverable scenario."
        )
        conflict = check_unit_count(len(with_area), municipal_unit_count)
        if conflict:
            notes.append(conflict)
        return UnitAreaResolution(
            average_existing_unit_sqm=average,
            source="unverified_schedule",
            certainty=Certainty.OCR_CANDIDATE,
            per_unit_detail_available=False,
            unit_count=len(with_area),
            notes=notes,
            has_unit_count_conflict=conflict is not None,
        )

    if existing_area_sqm and municipal_unit_count:
        ratio = (
            D5_EXISTING_PRIVATE_AREA_RATIO.value
            if existing_private_area_ratio is None
            else existing_private_area_ratio
        )
        if not 0 < ratio <= 1:
            raise ValueError("existing_private_area_ratio must be greater than 0 and at most 1")

        ratio_source = (
            D5_EXISTING_PRIVATE_AREA_RATIO.source
            if existing_private_area_ratio is None
            else (existing_private_area_ratio_source or "developer override; no external source supplied")
        )
        estimated_main_area = round(existing_area_sqm * ratio, 2)
        estimated_common_area = round(existing_area_sqm - estimated_main_area, 2)
        average = round(estimated_main_area / municipal_unit_count, 2)
        notes.append(
            f"No per-apartment schedule was extracted. The footprint fallback first gives "
            f"{existing_area_sqm} sqm of counted existing area (footprint x floors x k). "
            f"An explicit ESTIMATE of {ratio:.0%} private/main area is then applied: "
            f"{estimated_main_area} sqm private/main and {estimated_common_area} sqm "
            f"residual common/service area. Dividing only the estimated private/main area by "
            f"{municipal_unit_count} unit(s) gives {average} sqm per unit. The ratio source is: "
            f"{ratio_source}. This is not DATA, may not allocate compensation per household, "
            "and must not by itself upgrade an opportunity to ready."
        )
        return UnitAreaResolution(
            average_existing_unit_sqm=average,
            source="footprint_average",
            certainty=Certainty.ESTIMATE,
            per_unit_detail_available=False,
            unit_count=municipal_unit_count,
            notes=notes,
            estimated_main_area_sqm=estimated_main_area,
            estimated_common_service_area_sqm=estimated_common_area,
            estimated_main_area_ratio=ratio,
            estimated_main_area_ratio_source=ratio_source,
            estimated_main_area_ratio_status=D5_EXISTING_PRIVATE_AREA_RATIO.status.value,
        )

    notes.append("Neither a per-apartment schedule nor a footprint-derived area was available.")
    return UnitAreaResolution(
        average_existing_unit_sqm=None,
        source="none",
        certainty=Certainty.MISSING,
        per_unit_detail_available=False,
        unit_count=municipal_unit_count,
        notes=notes,
    )
