"""W10 (#115) -- reading the legend's own residential-area figure, when it
states one, so the §70א 70%-residential gate has an automatic candidate
instead of relying only on a person typing two numbers from scratch.
"""

from app.pipeline.extractor import ExtractionResult, _parse_residential_area


def test_residential_area_is_read_from_a_dedicated_row():
    text = 'שטח כולל 1,860.00 מ"ר\nשטח למגורים 1,450.00 מ"ר\n'
    assert _parse_residential_area(text) == 1450.0


def test_the_principal_use_wording_is_also_matched():
    assert _parse_residential_area('שטח עיקרי למגורים 980.50 מ"ר') == 980.5
    assert _parse_residential_area('שטח מגורים 700 מ"ר') == 700.0


def test_a_sheet_with_no_residential_row_yields_none():
    """Most permit sheets state only a building total -- absence is the
    normal case, not a failure (mirrors the unit schedule's own contract)."""
    assert _parse_residential_area('שטח כולל 1,860.00 מ"ר') is None
    assert _parse_residential_area("") is None


def test_only_the_first_match_is_taken_not_a_sum():
    """A legend that states the figure once, possibly repeated in a title
    block, did not mean to add it to itself."""
    text = 'שטח למגורים 1,450 מ"ר\nשטח למגורים 1,450 מ"ר\n'
    assert _parse_residential_area(text) == 1450.0


def test_extraction_result_carries_the_field_through():
    """Defaults to None so every existing caller/test that builds an
    ExtractionResult without this field keeps working unchanged."""
    bare = ExtractionResult(
        total_building_area_sqm=1860.0, confidence=90.0, method="tesseract_regex",
        is_plausible=True, plausibility_reason=None, requires_human_review=False,
    )
    assert bare.residential_area_sqm is None

    with_value = ExtractionResult(
        total_building_area_sqm=1860.0, confidence=90.0, method="tesseract_regex",
        is_plausible=True, plausibility_reason=None, requires_human_review=False,
        residential_area_sqm=1450.0,
    )
    assert with_value.residential_area_sqm == 1450.0
