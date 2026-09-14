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
from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evidence import DECIDING, SOURCE_MAX_AGE_DAYS, Certainty
from app.models.dwelling_unit import DwellingUnit
from app.pipeline.extractor import DwellingUnitReading

# How far the permit-sheet unit count may differ from the municipal address
# layer before the dossier calls it a conflict. Kept at zero: these two
# sources answer slightly different questions (what was permitted vs. what is
# registered today), so any gap is a real finding about the building, not
# noise to be tuned away.
UNIT_COUNT_TOLERANCE = 0


@dataclass
class UnitAreaResolution:
    """What the calculator may use, and what the dossier must say about it."""

    average_existing_unit_sqm: float | None
    # "verified_schedule" | "unverified_schedule" | "footprint_average" | "none"
    source: str
    certainty: Certainty
    # True only when every unit has its own confirmed area. Per-household
    # compensation may not be computed without this.
    per_unit_detail_available: bool
    unit_count: int | None
    notes: list[str]
    # Set when the schedule and the municipal address layer disagree on how
    # many units the building has. A confirmed schedule covering 1 of 28
    # apartments is confirmed for what it read and says nothing about the
    # other 27, so the disagreement has to block the average from deciding
    # rather than merely annotate it.
    has_unit_count_conflict: bool = False

    @property
    def may_decide(self) -> bool:
        """Whether this figure is allowed to drive a deliverable scenario."""
        return (
            self.certainty.value in DECIDING
            and self.average_existing_unit_sqm is not None
            and self.per_unit_detail_available
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


def _certainty_value(unit: DwellingUnit) -> str:
    certainty = unit.certainty
    return certainty.value if isinstance(certainty, Certainty) else str(certainty)


def _has_deciding_provenance(unit: DwellingUnit, *, now: datetime) -> bool:
    """Apply the repository's evidence gate to a per-apartment observation."""
    if unit.requires_human_review or _certainty_value(unit) not in DECIDING:
        return False
    if not unit.source_url or not unit.retrieved_at or unit.location is None:
        return False
    if unit.retrieved_at.tzinfo is None:
        return False
    age_days = (now - unit.retrieved_at).total_seconds() / 86400
    return 0 <= age_days <= SOURCE_MAX_AGE_DAYS


def select_scenario_average_input(
    resolution: UnitAreaResolution,
    *,
    fallback_value: float,
    blocking_inputs: Iterable[str],
) -> tuple[float, list[str]]:
    """Choose the scenario input without hiding whether it is fit to decide.

    The assumptions library intentionally marks the generic 70 sqm value as
    missing. A complete, verified building schedule replaces that blocker. A
    candidate schedule or footprint average may still be useful in a draft
    calculation, but keeps the field in ``missing_inputs`` so the result is
    never presented as deliverable.
    """
    blockers = [
        name
        for name in blocking_inputs
        if name != "average_existing_unit_sqm"
    ]
    value = resolution.average_existing_unit_sqm
    if value is None:
        value = fallback_value
    if not resolution.may_decide:
        blockers.append("average_existing_unit_sqm")
    return value, blockers


async def persist_unit_readings(
    session: AsyncSession,
    opportunity_id,
    readings: Sequence[DwellingUnitReading],
    *,
    method: str,
    source_url: str | None = None,
    content_sha256: str | None = None,
    retrieved_at: datetime | None = None,
    document_ref: str = "document",
    source_key_prefix: str | None = None,
    declared_unit_count: int | None = None,
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

    # Page order is not stable when the municipal archive changes. Prefer the
    # content digest as the durable document identity and keep document_ref
    # only as the human-readable location.
    stable_ref = source_key_prefix or content_sha256 or document_ref
    rows: list[DwellingUnit] = []
    batch_keys: set[str] = set()
    for index, reading in enumerate(readings, start=1):
        # Ordinal position is part of the key so an unlabelled row ("the
        # seventh row in the schedule") is still addressable and stable.
        unit_key = (reading.unit_label or f"row{index}")[:40]
        source_key = f"{stable_ref[: 119 - len(unit_key)]}#{unit_key}"
        if source_key in batch_keys:
            # A model can return the same label twice. Preserve both readings
            # for review instead of failing the whole transaction on the
            # unique constraint; the row suffix is deterministic on re-run.
            unit_key = f"{unit_key[:31]}:row{index}"
            source_key = f"{stable_ref[: 119 - len(unit_key)]}#{unit_key}"
        batch_keys.add(source_key)
        if source_key in confirmed:
            continue  # a person already settled this unit; leave their row in place
        row = DwellingUnit(
            opportunity_id=opportunity_id,
            building_id=building_id,
            source_key=source_key,
            unit_label=reading.unit_label[:40] if reading.unit_label else None,
            floor=reading.floor[:20] if reading.floor else None,
            # Keep the observed number even when it is implausible. The
            # plausibility fields prevent its use while preserving the exact
            # machine reading for audit and review.
            area_sqm=reading.area_sqm,
            declared_unit_count=declared_unit_count,
            is_plausible=reading.is_plausible,
            plausibility_reason=reading.plausibility_reason,
            certainty=_certainty_for(method, reading.is_plausible),
            requires_human_review=True,
            source_url=source_url,
            content_sha256=content_sha256,
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
    declared_unit_count: int | None = None,
    now: datetime | None = None,
) -> UnitAreaResolution:
    """Decide the average existing unit area, and how far it may be trusted.

    Order of preference:

    1. A schedule where every unit has been confirmed by a person. Decides,
       and carries per-unit detail, so per-household compensation is possible.
    2. A schedule still awaiting review. Displayed, never decides -- so a
       dossier cannot quietly rest on an unreviewed OCR reading.
    3. The footprint-derived building area divided by the municipal unit
       count. An `ESTIMATE`: it rests on `existing_area`, which is
       `footprint x floors x k` with k calibrated against a single permit.
       Never decides, and carries no per-unit detail.
    """
    notes: list[str] = []
    now = now or datetime.now(timezone.utc)
    units = list(units)
    stored_declared_counts = {
        count
        for unit in units
        if (count := getattr(unit, "declared_unit_count", None)) is not None
    }
    if declared_unit_count is None and len(stored_declared_counts) == 1:
        declared_unit_count = next(iter(stored_declared_counts))

    count_conflicts: list[str] = []
    if len(stored_declared_counts) > 1:
        count_conflicts.append(
            "Conflicting declared unit counts were stored for this schedule: "
            + ", ".join(str(count) for count in sorted(stored_declared_counts))
            + "."
        )
    source_count_conflict = check_unit_count(declared_unit_count, municipal_unit_count)
    if source_count_conflict:
        count_conflicts.append(source_count_conflict)

    with_area = [
        unit
        for unit in units
        if unit.area_sqm is not None
        and getattr(unit, "is_plausible", True)
        and _certainty_value(unit) != Certainty.MISSING.value
    ]

    if with_area:
        verified = [
            unit
            for unit in with_area
            if _has_deciding_provenance(unit, now=now)
        ]
        if verified and len(verified) == len(units):
            average = round(sum(u.area_sqm for u in verified) / len(verified), 2)
            notes.append(
                f"Average taken from {len(verified)} confirmed unit area(s) totalling "
                f"{round(sum(u.area_sqm for u in verified), 2)} sqm."
            )
            expected_count = declared_unit_count or municipal_unit_count
            coverage_conflict = (
                f"The confirmed schedule contains {len(verified)} unit(s), but the expected "
                f"building count is {expected_count}."
                if expected_count is not None and len(verified) != expected_count
                else None
            )
            if expected_count is None:
                notes.append(
                    "No declared or municipal unit count is available, so schedule completeness cannot be confirmed."
                )
            if coverage_conflict:
                count_conflicts.append(coverage_conflict)
            notes.extend(count_conflicts)
            complete = expected_count is not None and not count_conflicts
            return UnitAreaResolution(
                average_existing_unit_sqm=average,
                source="verified_schedule",
                certainty=Certainty.MANUALLY_VERIFIED,
                # Only a schedule that covers the whole building can support
                # per-household allocation: confirmed areas for 1 of 28
                # apartments leave 27 households with no figure of their own.
                per_unit_detail_available=complete,
                unit_count=len(verified),
                notes=notes,
                has_unit_count_conflict=bool(count_conflicts),
            )

        average = round(sum(u.area_sqm for u in with_area) / len(with_area), 2)
        notes.append(
            f"{len(with_area)} plausible unit area(s) were read from the permit sheet, "
            "but the schedule is incomplete, still awaiting review, or lacks current "
            "source provenance. It is displayed and cannot drive a deliverable scenario."
        )
        expected_count = declared_unit_count or municipal_unit_count
        if expected_count is not None and len(with_area) != expected_count:
            count_conflicts.append(
                f"The extracted schedule contains {len(with_area)} plausible unit area(s), "
                f"but the expected building count is {expected_count}."
            )
        notes.extend(count_conflicts)
        certainty_values = {_certainty_value(unit) for unit in with_area}
        if Certainty.AI_CANDIDATE.value in certainty_values:
            certainty = Certainty.AI_CANDIDATE
        elif Certainty.OCR_CANDIDATE.value in certainty_values:
            certainty = Certainty.OCR_CANDIDATE
        elif verified:
            certainty = Certainty.MANUALLY_VERIFIED
        else:
            certainty = Certainty.MISSING
        return UnitAreaResolution(
            average_existing_unit_sqm=average,
            source="unverified_schedule",
            certainty=certainty,
            per_unit_detail_available=False,
            unit_count=len(with_area),
            notes=notes,
            has_unit_count_conflict=bool(count_conflicts),
        )

    if existing_area_sqm and municipal_unit_count:
        average = round(existing_area_sqm / municipal_unit_count, 2)
        notes.append(
            f"No per-apartment schedule was extracted. The average is "
            f"{existing_area_sqm} sqm (footprint x floors x k) divided by "
            f"{municipal_unit_count} unit(s) -- a uniform average that matches no "
            "individual apartment, resting on a k calibrated against a single permit. "
            "It may not be used to allocate compensation per household."
        )
        return UnitAreaResolution(
            average_existing_unit_sqm=average,
            source="footprint_average",
            certainty=Certainty.ESTIMATE,
            per_unit_detail_available=False,
            unit_count=municipal_unit_count,
            notes=notes,
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
