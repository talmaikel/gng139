"""
Per-apartment area extraction, and the rules governing what it may decide.

The extraction tests exercise the regex layer directly rather than through
`extract_total_building_area`, which needs Tesseract and an image; the parsing
is where the behaviour under test lives.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.evidence import Certainty
from app.pipeline.extractor import (
    DwellingUnitReading,
    ExtractionResult,
    _parse_unit_count,
    _parse_unit_rows,
    _unit_plausibility,
)
from app.services.dwelling_units import (
    check_unit_count,
    persist_unit_readings,
    resolve_existing_unit_area,
    select_scenario_average_input,
)

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
    declared_unit_count: int | None = None
    is_plausible: bool = True
    source_url: str | None = "https://example.test/permit.pdf"
    retrieved_at: datetime | None = datetime(2026, 9, 14, tzinfo=timezone.utc)
    location: str | None = "page 2, row 1"


NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


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
        now=NOW,
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
        now=NOW,
    )
    assert resolution.has_unit_count_conflict is True
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


def test_verified_schedule_without_known_unit_count_must_not_decide():
    resolution = resolve_existing_unit_area(
        [FakeUnit(78.5, False, Certainty.MANUALLY_VERIFIED)],
        municipal_unit_count=None,
        existing_area_sqm=78.5,
        now=NOW,
    )
    assert resolution.source == "verified_schedule"
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False
    assert any("completeness cannot be confirmed" in note for note in resolution.notes)


def test_declared_count_can_confirm_complete_schedule():
    resolution = resolve_existing_unit_area(
        [FakeUnit(62.0, False, Certainty.MANUALLY_VERIFIED, declared_unit_count=2)] * 2,
        municipal_unit_count=None,
        existing_area_sqm=124.0,
        now=NOW,
    )
    assert resolution.may_decide is True
    assert resolution.unit_count == 2


def test_declared_and_municipal_count_conflict_blocks_verified_schedule():
    resolution = resolve_existing_unit_area(
        [FakeUnit(62.0, False, Certainty.MANUALLY_VERIFIED, declared_unit_count=2)] * 2,
        municipal_unit_count=3,
        existing_area_sqm=124.0,
        now=NOW,
    )
    assert resolution.has_unit_count_conflict is True
    assert resolution.may_decide is False


def test_verified_schedule_without_provenance_must_not_decide():
    resolution = resolve_existing_unit_area(
        [
            FakeUnit(
                70.0,
                False,
                Certainty.MANUALLY_VERIFIED,
                source_url=None,
            )
        ],
        municipal_unit_count=1,
        existing_area_sqm=70.0,
        now=NOW,
    )
    assert resolution.may_decide is False
    assert resolution.certainty is Certainty.MISSING


def test_stale_verified_schedule_must_not_decide():
    resolution = resolve_existing_unit_area(
        [
            FakeUnit(
                70.0,
                False,
                Certainty.MANUALLY_VERIFIED,
                retrieved_at=NOW - timedelta(days=31),
            )
        ],
        municipal_unit_count=1,
        existing_area_sqm=70.0,
        now=NOW,
    )
    assert resolution.may_decide is False


def test_unreviewed_ai_schedule_keeps_ai_certainty():
    resolution = resolve_existing_unit_area(
        [FakeUnit(78.5, True, Certainty.AI_CANDIDATE)],
        municipal_unit_count=1,
        existing_area_sqm=78.5,
    )
    assert resolution.certainty is Certainty.AI_CANDIDATE


def test_verified_schedule_replaces_only_the_average_area_blocker():
    resolution = resolve_existing_unit_area(
        [FakeUnit(70.0, False, Certainty.MANUALLY_VERIFIED)],
        municipal_unit_count=1,
        existing_area_sqm=70.0,
        now=NOW,
    )
    value, blockers = select_scenario_average_input(
        resolution,
        fallback_value=99.0,
        blocking_inputs=["average_existing_unit_sqm", "betterment_levy_ratio"],
    )
    assert value == 70.0
    assert blockers == ["betterment_levy_ratio"]


def test_unverified_average_remains_a_scenario_blocker():
    resolution = resolve_existing_unit_area(
        [FakeUnit(78.5, True, Certainty.OCR_CANDIDATE)],
        municipal_unit_count=1,
        existing_area_sqm=78.5,
    )
    value, blockers = select_scenario_average_input(
        resolution,
        fallback_value=70.0,
        blocking_inputs=["average_existing_unit_sqm"],
    )
    assert value == 78.5
    assert blockers == ["average_existing_unit_sqm"]


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


class _EmptyScalars:
    def scalars(self):
        return []


class _RecordingSession:
    def __init__(self):
        self.added = []

    async def execute(self, _statement):
        return _EmptyScalars()

    def add(self, row):
        self.added.append(row)


async def test_persistence_keeps_implausible_observation_for_audit():
    session = _RecordingSession()
    readings = [
        DwellingUnitReading(
            area_sqm=1250.0,
            unit_label="9",
            raw_text='דירה 9 1250 מ"ר',
            is_plausible=False,
            plausibility_reason="likely a building total",
        )
    ]

    rows = await persist_unit_readings(
        session,
        "opportunity-id",
        readings,
        method="tesseract_regex",
        source_url="https://example.test/permit.pdf",
        content_sha256="ab" * 32,
        retrieved_at=NOW,
        source_key_prefix="permit:page-2",
        declared_unit_count=12,
        replace_existing=False,
    )

    assert rows == session.added
    assert rows[0].area_sqm == 1250.0
    assert rows[0].is_plausible is False
    assert rows[0].certainty is Certainty.MISSING
    assert rows[0].content_sha256 == "ab" * 32
    assert rows[0].declared_unit_count == 12


async def test_persistence_keys_fit_database_limits():
    session = _RecordingSession()
    rows = await persist_unit_readings(
        session,
        "opportunity-id",
        [DwellingUnitReading(area_sqm=78.0, unit_label="x" * 60)],
        method="openai_gpt4o_mini",
        source_key_prefix="source" * 40,
        replace_existing=False,
    )
    assert len(rows[0].source_key) == 120
    assert len(rows[0].unit_label) == 40


async def test_duplicate_model_labels_do_not_collide():
    session = _RecordingSession()
    rows = await persist_unit_readings(
        session,
        "opportunity-id",
        [
            DwellingUnitReading(area_sqm=78.0, unit_label="1"),
            DwellingUnitReading(area_sqm=79.0, unit_label="1"),
        ],
        method="openai_gpt4o_mini",
        source_key_prefix="permit:page-2",
        replace_existing=False,
    )
    assert len({row.source_key for row in rows}) == 2
