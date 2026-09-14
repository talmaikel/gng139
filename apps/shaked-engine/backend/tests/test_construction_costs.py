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


def test_floor_count_picks_the_survey_band_instead_of_averaging():
    """The Shaked Alternative typically produces 7-9 floor buildings, which
    lands in the survey's high-rise band (7,200 for Herzliya) -- not the
    three-band average (7,366.67), which includes a low-rise figure that
    does not describe this kind of building at all."""
    region = REGIONAL_CONSTRUCTION_COSTS["herzliya"]
    r = resolve_construction_cost_per_sqm("herzliya", developer_value=None, floors=8)
    assert r.value_ils_per_sqm == region.high_rise_ils_per_sqm == 7_200.0
    assert r.method == "appraisers_survey_by_building_height"
    assert "בניין גבוה" in r.source


def test_floor_band_boundaries():
    region = REGIONAL_CONSTRUCTION_COSTS["herzliya"]
    assert region.cost_for_floors(4) == (region.low_rise_ils_per_sqm, "בניין נמוך")
    assert region.cost_for_floors(5) == (region.high_rise_ils_per_sqm, "בניין גבוה")
    assert region.cost_for_floors(9) == (region.high_rise_ils_per_sqm, "בניין גבוה")
    assert region.cost_for_floors(10) == (region.multi_story_ils_per_sqm, "בניין רב קומות")


def test_no_floor_count_still_falls_back_to_the_average():
    r = resolve_construction_cost_per_sqm("herzliya", developer_value=None, floors=None)
    region = REGIONAL_CONSTRUCTION_COSTS["herzliya"]
    assert r.value_ils_per_sqm == region.average_above_ground_ils_per_sqm
    assert r.method == "appraisers_survey_regional_average"


def test_developer_figure_beats_a_known_floor_count_too():
    r = resolve_construction_cost_per_sqm("herzliya", developer_value=9_500.0, floors=8)
    assert r.value_ils_per_sqm == 9_500.0
    assert r.method == "developer_input"


def test_uncovered_city_is_missing_not_guessed():
    r = resolve_construction_cost_per_sqm("some_other_city", developer_value=None)
    assert r.value_ils_per_sqm is None
    assert r.status == "missing"


def test_developer_figure_beats_an_uncovered_city_too():
    r = resolve_construction_cost_per_sqm("some_other_city", developer_value=8_800.0)
    assert r.value_ils_per_sqm == 8_800.0
    assert r.status == "data"
