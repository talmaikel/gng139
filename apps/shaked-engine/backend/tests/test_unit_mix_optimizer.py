import pytest

from app.services.unit_mix.optimizer import optimize_unit_mix
from app.services.unit_mix.schemas import UnitMixOptimizationInput, UnitTypeOption


def _input(**overrides):
    values = dict(
        existing_unit_areas_sqm=[65, 70, 75, 80, 85, 90],
        buildable_area_sqm=2400,
        main_area_ratio=0.78,
        compensation_sqm_per_existing_unit=12,
        default_compensation_sqm_per_existing_unit=18,
        default_compensation_label="herzliya_market_default_v1",
        unit_types=[
            UnitTypeOption(key="3r", rooms=3, area_sqm=75, price_per_sqm_ils=45_000),
            UnitTypeOption(key="4r", rooms=4, area_sqm=100, price_per_sqm_ils=43_000),
            UnitTypeOption(key="5r", rooms=5, area_sqm=125, price_per_sqm_ils=40_000),
        ],
    )
    values.update(overrides)
    return UnitMixOptimizationInput(**values)


def test_user_compensation_drives_tenant_and_developer_area():
    low = optimize_unit_mix(_input(compensation_sqm_per_existing_unit=12))
    high = optimize_unit_mix(_input(compensation_sqm_per_existing_unit=20))

    assert low.compensation_source == "user_defined"
    assert low.tenant_allocation_sqm == pytest.approx(sum([77, 82, 87, 92, 97, 102]))
    assert high.tenant_allocation_sqm - low.tenant_allocation_sqm == pytest.approx(6 * 8)
    assert high.developer_available_sqm < low.developer_available_sqm


def test_missing_user_compensation_uses_explicit_caller_default():
    result = optimize_unit_mix(_input(compensation_sqm_per_existing_unit=None))

    assert result.compensation_sqm_per_existing_unit == 18
    assert result.compensation_source == "herzliya_market_default_v1"


def test_optimizer_respects_herzliya_unit_multiplier_and_small_unit_share():
    result = optimize_unit_mix(_input())

    assert result.feasible
    assert result.candidates
    for candidate in result.candidates:
        assert 2.8 * 6 <= candidate.total_new_units <= 3.18 * 6
        assert candidate.small_unit_share >= 0.25
        assert candidate.micro_unit_share <= 0.10


def test_candidates_are_ranked_by_room_sensitive_market_revenue():
    result = optimize_unit_mix(_input())

    revenues = [candidate.gross_developer_revenue_ils for candidate in result.candidates]
    assert revenues == sorted(revenues, reverse=True)


def test_compensation_that_does_not_fit_returns_explicit_infeasible_result():
    result = optimize_unit_mix(
        _input(buildable_area_sqm=700, compensation_sqm_per_existing_unit=40)
    )

    assert not result.feasible
    assert result.candidates == []
    assert result.developer_available_sqm < 0
    assert any("do not fit" in warning for warning in result.warnings)


def test_no_hidden_compensation_magic_number():
    with pytest.raises(Exception):
        UnitMixOptimizationInput(
            existing_unit_areas_sqm=[70],
            buildable_area_sqm=1000,
            main_area_ratio=0.78,
            unit_types=[UnitTypeOption(key="3r", rooms=3, area_sqm=75, price_per_sqm_ils=40_000)],
        )
