import pytest

from app.evidence import Certainty
from app.services.dwelling_units import (
    FOOTPRINT_EXISTING_MAIN_AREA_RATIO,
    resolve_existing_unit_area,
)


def test_no_gramoshka_splits_existing_area_before_average():
    resolution = resolve_existing_unit_area(
        [],
        municipal_unit_count=10,
        existing_area_sqm=1000.0,
    )

    assert FOOTPRINT_EXISTING_MAIN_AREA_RATIO == 0.78
    assert resolution.source == "footprint_average"
    assert resolution.certainty is Certainty.ESTIMATE
    assert resolution.estimated_main_area_sqm == 780.0
    assert resolution.estimated_common_service_area_sqm == 220.0
    assert resolution.estimated_main_area_ratio == 0.78
    assert resolution.average_existing_unit_sqm == 78.0
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False


def test_footprint_split_does_not_override_real_schedule():
    class Unit:
        area_sqm = 82.0
        requires_human_review = False
        certainty = Certainty.MANUALLY_VERIFIED

    resolution = resolve_existing_unit_area(
        [Unit(), Unit()],
        municipal_unit_count=2,
        existing_area_sqm=1000.0,
    )

    assert resolution.source == "verified_schedule"
    assert resolution.average_existing_unit_sqm == 82.0
    assert resolution.estimated_main_area_sqm is None
    assert resolution.estimated_common_service_area_sqm is None
    assert resolution.may_decide is True


def test_footprint_split_is_explicitly_described_as_estimate():
    resolution = resolve_existing_unit_area(
        [],
        municipal_unit_count=28,
        existing_area_sqm=1409.6,
    )

    assert resolution.average_existing_unit_sqm == pytest.approx(39.27, abs=0.01)
    note = " ".join(resolution.notes)
    assert "78%" in note
    assert "common/service" in note
    assert "not DATA" in note
