import pytest

from app.evidence import Certainty
from app.services.dwelling_units import (
    FOOTPRINT_EXISTING_MAIN_AREA_RATIO,
    resolve_existing_unit_area,
)
from app.services.economic.existing_area_assumptions import D5_EXISTING_PRIVATE_AREA_RATIO


def test_no_gramoshka_uses_sourced_d5_fallback_before_average():
    resolution = resolve_existing_unit_area(
        [],
        municipal_unit_count=10,
        existing_area_sqm=1000.0,
    )

    assert FOOTPRINT_EXISTING_MAIN_AREA_RATIO == D5_EXISTING_PRIVATE_AREA_RATIO.value == 0.85
    assert resolution.source == "footprint_average"
    assert resolution.certainty is Certainty.ESTIMATE
    assert resolution.estimated_main_area_sqm == 850.0
    assert resolution.estimated_common_service_area_sqm == 150.0
    assert resolution.estimated_main_area_ratio == 0.85
    assert resolution.estimated_main_area_ratio_status == "estimate"
    assert "D5 preliminary calibration" in resolution.estimated_main_area_ratio_source
    assert resolution.average_existing_unit_sqm == 85.0
    assert resolution.may_decide is False
    assert resolution.per_unit_detail_available is False


def test_developer_can_override_ratio_but_result_stays_estimate():
    resolution = resolve_existing_unit_area(
        [],
        municipal_unit_count=10,
        existing_area_sqm=1000.0,
        existing_private_area_ratio=0.90,
        existing_private_area_ratio_source="developer scenario override",
    )

    assert resolution.estimated_main_area_sqm == 900.0
    assert resolution.estimated_common_service_area_sqm == 100.0
    assert resolution.estimated_main_area_ratio == 0.90
    assert resolution.estimated_main_area_ratio_source == "developer scenario override"
    assert resolution.average_existing_unit_sqm == 90.0
    assert resolution.certainty is Certainty.ESTIMATE
    assert resolution.may_decide is False


def test_invalid_override_is_rejected():
    with pytest.raises(ValueError):
        resolve_existing_unit_area(
            [],
            municipal_unit_count=10,
            existing_area_sqm=1000.0,
            existing_private_area_ratio=1.2,
        )


def test_footprint_split_does_not_override_real_schedule():
    class Unit:
        area_sqm = 82.0
        requires_human_review = False
        certainty = Certainty.MANUALLY_VERIFIED

    resolution = resolve_existing_unit_area(
        [Unit(), Unit()],
        municipal_unit_count=2,
        existing_area_sqm=1000.0,
        existing_private_area_ratio=0.80,
        existing_private_area_ratio_source="ignored because schedule is verified",
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

    assert resolution.average_existing_unit_sqm == pytest.approx(42.79, abs=0.01)
    note = " ".join(resolution.notes)
    assert "85%" in note
    assert "common/service" in note
    assert "not DATA" in note
    assert "must not by itself upgrade" in note
