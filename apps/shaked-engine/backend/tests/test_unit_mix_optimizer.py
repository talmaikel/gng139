import pytest

from app.services.economic.schemas import FeasibilityInput
from app.services.unit_mix.optimizer import optimize_unit_mix
from app.services.unit_mix.schemas import UnitMixOptimizationInput, UnitTypeOption


def _economic_input(**overrides):
    values = dict(
        plot_area_sqm=900,
        existing_units=6,
        buildable_area_sqm=2400,
        sale_price_per_sqm=42_000,
        construction_cost_per_sqm=10_000,
        main_area_ratio=0.78,
        underground_ratio=0.40,
        underground_cost_per_sqm=6_000,
        soft_cost_ratio=0.15,
        demolition_cost_per_unit=150_000,
        average_existing_unit_sqm=77.5,
        tenant_compensation_sqm_per_existing_unit=12,
        tenant_rent_months=42,
        tenant_monthly_rent_ils=7_500,
        tenant_moving_cost_ils=10_000,
        tenant_legal_cost_per_unit_ils=30_000,
        marketing_ratio=0.025,
        guarantees_ratio=0.0125,
        finance_ratio=0.06,
        betterment_levy_rate=0.25,
        betterment_base_ils=0,
        sale_price_includes_vat=True,
        vat_rate=0.18,
        developer_profit_target_ratio=0.20,
    )
    values.update(overrides)
    return FeasibilityInput(**values)


def _input(**overrides):
    values = dict(
        existing_unit_areas_sqm=[65, 70, 75, 80, 85, 90],
        buildable_area_sqm=2400,
        main_area_ratio=0.78,
        economic_input=_economic_input(),
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


def test_candidates_are_ranked_by_report_zero_projected_profit():
    result = optimize_unit_mix(_input())

    ranking = [
        (
            candidate.projected_profit_ils,
            candidate.profit_margin_on_cost_ratio,
            candidate.gross_developer_revenue_ils,
            -candidate.unused_developer_sqm,
        )
        for candidate in result.candidates
    ]
    assert ranking == sorted(ranking, reverse=True)
    assert all(candidate.total_cost_ils > 0 for candidate in result.candidates)
    assert all(candidate.developer_revenue_ils > 0 for candidate in result.candidates)


def test_room_sensitive_revenue_is_passed_exactly_to_report_zero():
    result = optimize_unit_mix(_input())
    best = result.candidates[0]

    # Report 0 removes VAT from the exact enumerated developer-apartment value.
    assert best.developer_revenue_ils == pytest.approx(
        best.gross_developer_revenue_ils / 1.18,
        abs=0.02,
    )


def test_compensation_change_recalculates_profit_not_only_area():
    low = optimize_unit_mix(_input(compensation_sqm_per_existing_unit=12))
    high = optimize_unit_mix(_input(compensation_sqm_per_existing_unit=20))

    assert low.candidates and high.candidates
    assert low.candidates[0].projected_profit_ils != high.candidates[0].projected_profit_ils


def test_missing_economic_input_is_carried_to_candidate_delivery_status():
    result = optimize_unit_mix(_input(economic_missing_inputs=["betterment_base_ils"]))

    assert result.candidates
    assert not result.candidates[0].economics_deliverable
    assert any("not deliverable" in warning for warning in result.warnings)


def test_compensation_that_does_not_fit_returns_explicit_infeasible_result():
    result = optimize_unit_mix(
        _input(
            buildable_area_sqm=700,
            economic_input=_economic_input(buildable_area_sqm=700),
            compensation_sqm_per_existing_unit=40,
        )
    )

    assert not result.feasible
    assert result.candidates == []
    assert result.developer_available_sqm < 0
    assert any("do not fit" in warning for warning in result.warnings)


def test_economic_input_must_match_per_apartment_and_rights_inputs():
    with pytest.raises(ValueError, match="existing_units"):
        _input(economic_input=_economic_input(existing_units=7))

    with pytest.raises(ValueError, match="buildable_area_sqm"):
        _input(economic_input=_economic_input(buildable_area_sqm=2300))


def test_no_hidden_compensation_magic_number():
    with pytest.raises(Exception):
        UnitMixOptimizationInput(
            existing_unit_areas_sqm=[70],
            buildable_area_sqm=1000,
            main_area_ratio=0.78,
            economic_input=FeasibilityInput(
                plot_area_sqm=500,
                existing_units=1,
                buildable_area_sqm=1000,
                sale_price_per_sqm=40_000,
                construction_cost_per_sqm=10_000,
            ),
            unit_types=[UnitTypeOption(key="3r", rooms=3, area_sqm=75, price_per_sqm_ils=40_000)],
        )
