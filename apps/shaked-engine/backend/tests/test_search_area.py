"""אימות אזור החיפוש המצויר — PRD MAP-01.

כל שלוש הבדיקות חייבות ליפול *לפני* שנוגעים בבסיס הנתונים: פוליגון פסול
אינו שאילתה יקרה, הוא שגיאת קלט.
"""
import pytest
from shapely.geometry import shape

from app.cities.herzliya.boundary import boundary_itm, search_polygon_wkt, validate_search_area


def square(lon, lat, d=0.002):
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat],
                                                [lon + d, lat + d], [lon, lat + d], [lon, lat]]]}


IN_HERZLIYA = square(34.840, 32.163)


def test_the_official_boundary_is_herzliya():
    b = boundary_itm()
    assert 20e6 < b.area < 30e6          # 24.2 קמ״ר
    assert b.is_valid


def test_a_small_area_inside_the_city_passes():
    assert validate_search_area(IN_HERZLIYA).area > 0


def test_an_area_outside_the_city_is_refused_however_small():
    with pytest.raises(ValueError, match="הגבול העירוני"):
        validate_search_area(square(34.780, 32.070))     # תל אביב


def test_an_area_that_straddles_the_boundary_is_refused():
    """לא מספיק שהמרכז בתוך העיר — הפוליגון כולו חייב להיות בפנים."""
    with pytest.raises(ValueError, match="הגבול העירוני"):
        validate_search_area(square(34.824, 32.160, 0.004))


def test_too_large_an_area_is_refused():
    with pytest.raises(ValueError, match="דונם"):
        validate_search_area(square(34.840, 32.163, 0.02))


def test_a_self_crossing_polygon_is_refused():
    bad = {"type": "Polygon", "coordinates": [[[34.84, 32.16], [34.85, 32.17],
                                               [34.84, 32.17], [34.85, 32.16], [34.84, 32.16]]]}
    with pytest.raises(ValueError, match="חצייה עצמית"):
        validate_search_area(bad)


def test_the_wkt_handed_to_postgis_is_validated_first():
    """‏`search_polygon_wkt` אינו מסלול עוקף — הוא מאמת לפני שהוא בונה WKT."""
    with pytest.raises(ValueError):
        search_polygon_wkt(square(34.780, 32.070))
    assert search_polygon_wkt(IN_HERZLIYA).startswith("POLYGON((")


def test_all_seeded_candidates_lie_inside_the_boundary():
    """בדיקת שפיות על הגבול עצמו: אם הוא שגוי, הוא יפסול מועמדים אמיתיים."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[4] / "POC" / "layer_a" / "data" / "parcels_700.geojson.json"
    if not p.exists():
        pytest.skip("layer_a data not present")
    from app.geo import itm
    b = boundary_itm().buffer(1)
    sample = list(json.loads(p.read_text(encoding="utf-8")).values())[:50]
    assert all(b.covers(itm(shape(x["geometry"]))) for x in sample)
