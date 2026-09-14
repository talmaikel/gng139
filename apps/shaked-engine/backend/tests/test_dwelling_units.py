"""
Per-apartment area extraction, and the rules governing what it may decide.

The extraction tests exercise the regex layer directly rather than through
`extract_total_building_area`, which needs Tesseract and an image; the parsing
is where the behaviour under test lives.
"""

from dataclasses import dataclass

import pytest

from app.evidence import Certainty
from app.pipeline.extractor import (
    DwellingUnitReading,
    ExtractionResult,
    _parse_declared_floor_count,
    _parse_unit_count,
    _parse_unit_rows,
    _unit_plausibility,
)
from app.services.dwelling_units import check_unit_count, resolve_existing_unit_area
from app.services.economic.assumptions import get_assumptions
from app.worker import _average_existing_unit_input, _select_observed_floor_count

HEBREW_SCHEDULE = """טבלת שטחים
דירה 1 קומה 1 78.50 מ"ר
דירה 2 קומה 1 64.20 מ"ר
דירה 3 קומה 2 78.50 מ"ר
סה"כ 3 יח"ד
"""

COLUMNAR_SCHEDULE = """
1   1   78.50
2   1   64.20
3   2   103.00
"""


@dataclass
class FakeUnit:
    """Stands in for a DwellingUnit row without needing a database."""

    area_sqm: float | None
    requires_human_review: bool
    certainty: Certainty


# ── parsing ────────────────────────────────────────────────────────────────


def test_hebrew_schedule_yields_one_row_per_apartment():
    units = _parse_unit_rows(HEBREW_SCHEDULE)
    assert [u.unit_label for u in units] == ["1", "2", "3"]
    assert [u.area_sqm for u in units] == [78.5, 64.2, 78.5]
    assert [u.floor for u in units] == ["1", "1", "2"]


def test_columnar_schedule_is_read_without_hebrew_labels():
    units = _parse_unit_rows(COLUMNAR_SCHEDULE)
    assert [u.area_sqm for u in units] == [78.5, 64.2, 103.0]


def test_declared_count_is_read_separately_from_the_rows():
    """The summary line can be legible when the schedule is not, and vice
    versa; they are two observations, not one."""
    assert _parse_unit_count(HEBREW_SCHEDULE) == 3
    assert _parse_unit_count("הבניין כולל 6 יחידות דיור") == 6
    assert _parse_unit_count(COLUMNAR_SCHEDULE) is None


def test_explicit_building_floor_count_is_read():
    assert _parse_declared_floor_count("מבנה בן 4 קומות") == 4
    assert _parse_declared_floor_count('סה"כ 5 קומות בבניין') == 5
    assert _parse_declared_floor_count("מספר קומות: 3") == 3


def test_apartment_floor_does_not_become_building_floor_count():
    """A schedule reaching floor 3 does not prove the legal/building count.
    Pilotis, roof levels or a floor without a dwelling row may exist."""
    assert _parse_declared_floor_count('דירה 7 קומה 3 81.20 מ"ר') is None
    assert _parse_declared_floor_count(HEBREW_SCHEDULE) is None


def test_gush_and_parcel_numbers_are_not_mistaken_for_units():
    assert _parse_unit_rows("גוש 6537 חלקה 222 תשריט מאושר 1961") == []
    assert _parse_unit_count("גוש 6537 חלקה 222") is None


def test_repeated_schedule_rows_are_deduplicated():
    """A schedule reprinted in a title block would otherwise double the count."""
    units = _parse_unit_rows('דירה 1 קומה 1 78.50 מ"ר\nדירה 1 קומה 1 78.50 מ"ר')
    assert len(units) == 1


def test_out_of_range_area_is_flagged_not_dropped():
    """A building total landing in the unit column is the case the bounds
    check exists for, so it must be matched and flagged -- narrowing the
    pattern so it never matches would hide it instead."""
    units = _parse_unit_rows('דירה 9 קומה 1 1250.00 מ"ר')
    assert len(units) == 1
    assert units[0].is_plausible is False
    assert "building total" in units[0].plausibility_reason


def test_unit_plausibility_bounds():
    assert _unit_plausibility(78.5)[0] is True
    assert _unit_plausibility(3.0)[0] is False
    assert _unit_plausibility(900.0)[0] is False
    assert _unit_plausibility(None)[0] is False


def test_units_total_area_sums_only_what_was_read():
    result = ExtractionResult(
        total_building_area_sqm=None,
        confidence=0.0,
        method="tesseract_regex",
        is_plausible=False,
        plausibility_reason=None,
        requires_human_review=True,
        units=[DwellingUnitReading(area_sqm=78.5), DwellingUnitReading(area_sqm=None)],
    )
    assert result.units_total_area_sqm == 78.5


# ── observed floor count in the dossier ───────────────────────────────────


def _floor_result(value, *, confidence=80.0, page="document 1, page 1", method="tesseract_regex"):
    return {
        "declared_floor_count": value,
        "confidence": confidence,
        "page_ref": page,
        "source_url": "https://example.test/permit.pdf",
        "method": method,
    }


def test_one_declared_floor_count_is_exposed_but_requires_review():
    observation = _select_observed_floor_count([_floor_result(4)])
    assert observation["value"] == 4
    assert observation["status"] == "observed_unverified"
    assert observation["requires_human_review"] is True
    assert observation["has_conflict"] is False
    assert observation["page_ref"] == "document 1, page 1"


def test_repeated_same_floor_count_is_not_a_conflict():
    observation = _select_observed_floor_count(
        [_floor_result(4, confidence=70), _floor_result(4, confidence=90, page="document 2, page 3")]
    )
    assert observation["value"] == 4
    assert observation["has_conflict"] is False
    assert observation["page_ref"] == "document 2, page 3"


def test_conflicting_permit_floor_counts_are_not_auto_resolved():
    observation = _select_observed_floor_count([_floor_result(3), _floor_result(4)])
    assert observation["value"] is None
    assert observation["status"] == "conflict"
    assert observation["has_conflict"] is True
    assert {c["value"] for c in observation["candidates"]} == {3, 4}


def test_missing_floor_count_is_explicit_not_guessed():
    observation = _select_observed_floor_count([_floor_result(None)])
    assert observation["value"] is None
    assert observation["status"] == "missing"


# ── the cross-check against the municipal layer ────────────────────────────


def test_matching_unit_counts_are_not_a_conflict():
    assert check_unit_count(6, 6) is None


def test_disagreeing_unit_counts_are_reported():
    note = check_unit_count(6, 28)
    assert note is not None and "6" in note and "28" in note


def test_conflict_is_not_raised_when_one_side_is_unknown():
    assert check_unit_count(None, 28) is None
    assert check_unit_count(6, None) is None


# ── what may decide a scenario ─────────────────────────────────────────────


def test_fully_verified_schedule_decides_and_supports_per_household():
    resolution = resolve_existing_unit_area(
        [FakeUnit(70.0, False, Certainty.MANUALLY_VERIFIED)] * 28,
        municipal_unit_count=28,
        existing_area_sqm=1409.6,
    )
    assert resolution.source == "verified_schedule"
    assert resolution.may_decide is True
    assert resolution.per_unit_detail_available is True
    assert resolution.average_existing_unit_sqm == 70.0


def test_verified_but_partial_schedule_must_not_decide():
    """Confirmed areas for 1 of 28 apartments are confirmed for what they
    read and say nothing about the other 27."""
    resolution = resolve_existing_unit_area(
        [FakeUnit(78.5, False, Certainty.MANUALLY_VERIFIED)],
        municipal_unit_count=28,
        existing_area_sqm=1400.0,
    )
    assert resolution.has_unit_count_conflict is True
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False


def test_verified_schedule_without_independent_count_must_not_decide():
    resolution = resolve_existing_unit_area(
        [FakeUnit(70.0, False, Certainty.MANUALLY_VERIFIED)] * 4,
        municipal_unit_count=None,
        existing_area_sqm=280.0,
    )
    assert resolution.source == "verified_schedule"
    assert resolution.schedule_complete is False
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False


def test_verified_rows_do_not_hide_a_schedule_row_with_no_area():
    resolution = resolve_existing_unit_area(
        [
            FakeUnit(70.0, False, Certainty.MANUALLY_VERIFIED),
            FakeUnit(None, True, Certainty.MISSING),
        ],
        municipal_unit_count=1,
        existing_area_sqm=140.0,
    )
    assert resolution.source == "unverified_schedule"
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False


def test_unreviewed_ocr_schedule_is_shown_but_cannot_decide():
    resolution = resolve_existing_unit_area(
        [FakeUnit(78.5, True, Certainty.OCR_CANDIDATE)] * 4,
        municipal_unit_count=4,
        existing_area_sqm=1400.0,
    )
    assert resolution.source == "unverified_schedule"
    assert resolution.average_existing_unit_sqm == 78.5  # displayed
    assert resolution.may_decide is False                # but never decides
    assert resolution.per_unit_detail_available is False


def test_partially_verified_schedule_does_not_count_as_verified():
    resolution = resolve_existing_unit_area(
        [
            FakeUnit(78.5, False, Certainty.MANUALLY_VERIFIED),
            FakeUnit(64.2, True, Certainty.OCR_CANDIDATE),
        ],
        municipal_unit_count=2,
        existing_area_sqm=1400.0,
    )
    assert resolution.source == "unverified_schedule"
    assert resolution.may_decide is False


def test_footprint_average_is_an_estimate_that_cannot_decide():
    resolution = resolve_existing_unit_area(
        [], municipal_unit_count=28, existing_area_sqm=1409.6
    )
    assert resolution.source == "footprint_average"
    assert resolution.certainty is Certainty.ESTIMATE
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False
    assert resolution.average_existing_unit_sqm == pytest.approx(50.34, abs=0.01)
    assert any("uniform average" in note for note in resolution.notes)


def test_nothing_available_is_reported_as_missing_not_guessed():
    resolution = resolve_existing_unit_area(
        [], municipal_unit_count=None, existing_area_sqm=None
    )
    assert resolution.average_existing_unit_sqm is None
    assert resolution.certainty is Certainty.MISSING
    assert resolution.may_decide is False


def test_verified_schedule_replaces_the_missing_city_placeholder():
    assumptions = get_assumptions("herzliya")
    resolution = resolve_existing_unit_area(
        [FakeUnit(72.0, False, Certainty.MANUALLY_VERIFIED)] * 4,
        municipal_unit_count=4,
        existing_area_sqm=288.0,
    )
    value, blockers, report = _average_existing_unit_input(assumptions, resolution)
    assert value == 72.0
    assert "average_existing_unit_sqm" not in blockers
    assert report["status"] == "manually_verified"
    assert report["source"] == "verified_schedule"


def test_missing_schedule_reports_and_blocks_the_city_placeholder_once():
    assumptions = get_assumptions("herzliya")
    resolution = resolve_existing_unit_area(
        [], municipal_unit_count=None, existing_area_sqm=None
    )
    value, blockers, report = _average_existing_unit_input(assumptions, resolution)
    assert value == assumptions.average_existing_unit_sqm.value
    assert blockers.count("average_existing_unit_sqm") == 1
    assert report["status"] == "missing"
    assert report["source"] == assumptions.average_existing_unit_sqm.source
