import pytest

from app.services.economic.calculator import calculate_feasibility
from app.services.economic.schemas import FeasibilityInput


def _input(**overrides):
    values = dict(
        plot_area_sqm=900,
        existing_units=6,
        buildable_area_sqm=2400,
        sale_price_per_sqm=42_000,
        construction_cost_per_sqm=10_000,
        main_area_ratio=0.78,
        average_existing_unit_sqm=77.5,
        tenant_compensation_sqm_per_existing_unit=12,
    )
    values.update(overrides)
    return FeasibilityInput(**values)


def test_without_b15_override_generic_report_zero_behavior_is_unchanged():
    inputs = _input()
    result = calculate_feasibility(inputs)
    net_price = inputs.sale_price_per_sqm / (1 + inputs.vat_rate)

    # ‏16.09 · ועוד מרפסות היזם, בחצי מחיר (דוחות 0).
    assert result.developer_revenue_ils == pytest.approx(
        result.developer_allocation_sqm * net_price + result.balcony_revenue_ils,
        abs=0.02,
    )
    assert result.balcony_revenue_ils > 0


def test_b15_exact_revenue_does_not_sell_unused_residual_area():
    gross_exact_revenue = 41_250_000
    inputs = _input(developer_sale_revenue_ils=gross_exact_revenue)
    result = calculate_feasibility(inputs)

    assert result.developer_revenue_ils == pytest.approx(
        gross_exact_revenue / (1 + inputs.vat_rate),
        abs=0.02,
    )
    # ‏16.09 · ההכנסה היא של היזם בלבד, והתמהיל כבר מתמחר דירה שלמה —
    # ולכן אין מרפסות נוספות מעליו.
    assert result.total_revenue_ils == pytest.approx(result.developer_revenue_ils, abs=0.02)
    assert result.balcony_revenue_ils == 0.0
    assert result.owners_flats_value_ils > 0
