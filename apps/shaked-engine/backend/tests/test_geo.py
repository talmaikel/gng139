import pytest
from shapely.geometry import Polygon, box, mapping, shape

from app.geo import center_selected, circle_polygon, itm, match_parcels, pair_geometry, validate_polygon, wgs

# Ported from POC/tests/test_core.py, assertions unchanged.


def shape_equal(a, b):
    return shape(a).hausdorff_distance(shape(b)) < 1e-7


def test_coordinate_roundtrip_and_area():
    g = mapping(box(34.84, 32.16, 34.841, 32.161))
    assert shape_equal(g, wgs(itm(g)))
    assert 9000 < itm(g).area < 12000


def test_centroid_boundary_inclusive():
    assert center_selected(box(-1, -1, 1, 1), box(0, 0, 10, 10))
    assert not center_selected(box(-3, -3, -1, -1), box(0, 0, 10, 10))


def test_polygon_city_area_and_self_intersection():
    g = mapping(box(34.84, 32.16, 34.841, 32.161))
    p = itm(g)
    assert validate_polygon(g, p.buffer(10), 20000).is_valid
    with pytest.raises(ValueError):
        validate_polygon(g, p.buffer(10), 100)
    with pytest.raises(ValueError):
        validate_polygon(g, p.buffer(-1), 20000)
    with pytest.raises(ValueError):
        validate_polygon(mapping(Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])), p, 20000)


def test_circle_is_metric_and_must_fit_city():
    boundary = itm(mapping(box(34.83, 32.15, 34.86, 32.18)))
    circle = circle_polygon({"lat": 32.165, "lon": 34.845}, 100, boundary, 250, 250000)
    assert 31000 < circle.area < 31500
    with pytest.raises(ValueError, match="250"):
        circle_polygon({"lat": 32.165, "lon": 34.845}, 251, boundary, 250, 250000)


def test_parcel_overlap_not_nearest_neighbor():
    a = {"id": "a", "geometry": mapping(box(0, 0, 5, 10))}
    b = {"id": "b", "geometry": mapping(box(5, 0, 10, 10))}
    matches = match_parcels(box(0, 0, 10, 10), [b, a])
    assert [x[1]["id"] for x in matches] == ["a", "b"]
    assert matches[0][0] == 0.5


def test_pair_requires_shared_boundary_and_evidence():
    assert pair_geometry(box(0, 0, 1, 1), box(1, 0, 2, 1), False) is None
    assert pair_geometry(box(0, 0, 1, 1), box(1, 0, 2, 1), True).area == 2
    assert pair_geometry(box(0, 0, 1, 1), box(1, 1, 2, 2), True) is None


# ---- added with the port: the city check is the boundary, not a lat/lon box ----


def test_circle_outside_the_boundary_is_refused():
    boundary = itm(mapping(box(34.83, 32.15, 34.86, 32.18)))
    with pytest.raises(ValueError, match="הגבול העירוני"):
        circle_polygon({"lat": 32.30, "lon": 34.85}, 100, boundary, 250, 250000)
