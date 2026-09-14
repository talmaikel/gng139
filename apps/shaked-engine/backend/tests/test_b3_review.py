import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.v1.dossiers import DwellingUnitReviewRequest, _apply_dwelling_review
from app.evidence import Certainty
from app.models.dwelling_unit import DwellingUnit
from app.services.dwelling_units import resolve_existing_unit_area


def unit(label: str, area: float | None, *, with_source: bool = True) -> DwellingUnit:
    return DwellingUnit(
        opportunity_id=uuid.uuid4(),
        source_key=f"doc#{label}",
        unit_label=label,
        floor="2",
        area_sqm=area,
        certainty=Certainty.OCR_CANDIDATE,
        requires_human_review=True,
        source_url="https://example.test/permit" if with_source else None,
        retrieved_at=datetime.now(timezone.utc) if with_source else None,
        location=f"page 2 · row {label}" if with_source else None,
        method="tesseract_regex",
        raw_text=f"דירה {label} קומה 2 {area} מ״ר",
    )


def test_confirm_requires_traceable_source_provenance():
    row = unit("1", 78.5, with_source=False)
    with pytest.raises(HTTPException) as exc:
        _apply_dwelling_review(row, DwellingUnitReviewRequest(action="confirm"))
    assert exc.value.status_code == 422
    assert row.requires_human_review is True


def test_human_can_correct_then_confirm_a_complete_schedule():
    rows = [unit("1", 76.0), unit("2", 82.0)]

    _apply_dwelling_review(
        rows[0],
        DwellingUnitReviewRequest(action="confirm", floor="1", area_sqm=77.0),
    )
    _apply_dwelling_review(rows[1], DwellingUnitReviewRequest(action="confirm"))

    assert rows[0].floor == "1"
    assert rows[0].area_sqm == 77.0
    assert all(row.certainty is Certainty.MANUALLY_VERIFIED for row in rows)
    assert all(row.requires_human_review is False for row in rows)

    resolution = resolve_existing_unit_area(
        rows,
        municipal_unit_count=2,
        existing_area_sqm=None,
    )
    assert resolution.average_existing_unit_sqm == 79.5
    assert resolution.schedule_complete is True
    assert resolution.per_unit_detail_available is True
    assert resolution.may_decide is True


def test_partial_confirmation_stays_non_deciding():
    rows = [unit("1", 77.0), unit("2", 82.0)]
    _apply_dwelling_review(rows[0], DwellingUnitReviewRequest(action="confirm"))

    resolution = resolve_existing_unit_area(
        rows,
        municipal_unit_count=2,
        existing_area_sqm=None,
    )
    assert resolution.may_decide is False
    assert resolution.schedule_complete is False


def test_reject_never_turns_bad_ocr_into_a_fact():
    row = unit("1", 188.0)
    _apply_dwelling_review(row, DwellingUnitReviewRequest(action="reject"))

    assert row.area_sqm is None
    assert row.certainty is Certainty.MISSING
    assert row.requires_human_review is True
    assert row.method == "manual_rejected"

    resolution = resolve_existing_unit_area(
        [row],
        municipal_unit_count=1,
        existing_area_sqm=None,
    )
    assert resolution.may_decide is False
