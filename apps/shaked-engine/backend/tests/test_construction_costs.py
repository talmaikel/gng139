"""B2 -- construction-cost resolution: developer figure beats the appraisers'
regional survey, which beats nothing at all."""

from app.services.economic.construction_costs import (
    REGIONAL_CONSTRUCTION_COSTS,
    REPORT_SOURCE,
    resolve_construction_cost_per_sqm,
)


def test_developer_figure_always_wins():
    r = resolve_construction_cost_per_sqm("herzliya", developer_value=9_500.0)
    assert r.value_ils_per_sqm == 9_500.0
    assert r.status == "data"
    assert r.method == "developer_input"
    assert r.source == "developer_provided"


def test_falls_back_to_the_regional_survey_average():
    r = resolve_construction_cost_per_sqm("herzliya", developer_value=None)
    region = REGIONAL_CONSTRUCTION_COSTS["herzliya"]
    assert r.value_ils_per_sqm == region.average_above_ground_ils_per_sqm
    assert r.value_ils_per_sqm == round((7_000.0 + 7_200.0 + 7_900.0) / 3, 2)
    # An average across three building-height bands is not a project-specific
    # fact, so it is reported as an estimate even though every input to it is
    # a real, cited survey figure.
    assert r.status == "estimate"
    assert REPORT_SOURCE in r.source
    assert region.region_label in r.source


def test_uncovered_city_is_missing_not_guessed():
    r = resolve_construction_cost_per_sqm("some_other_city", developer_value=None)
    assert r.value_ils_per_sqm is None
    assert r.status == "missing"


def test_developer_figure_beats_an_uncovered_city_too():
    r = resolve_construction_cost_per_sqm("some_other_city", developer_value=8_800.0)
    assert r.value_ils_per_sqm == 8_800.0
    assert r.status == "data"
