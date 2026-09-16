"""W1 · השטח לפי מדיניות הרצליה — מעטפת בתוך קווי הבניין והנסיגות (#106)."""
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from app.cities.herzliya import policy_envelope as pe

BIG_CAP = 100_000.0


def _run(geom, floors_low, floors_high=None, cap=BIG_CAP, frontages=1, plot=None):
    res, why = pe.compute(geom, plot_sqm=plot, floors_low=floors_low,
                          floors_high=floors_high, cap_400_sqm=cap, frontages=frontages)
    assert why is None, why
    return res


def test_a_rectangle_worked_by_hand_at_seven_floors():
    """‏30×40 מ׳, רחוב 9–10 מ׳ (7 קומות): קדמי 5, צד 4, אחורי 5, ונסיגה של 3 מ׳
    לקדמית ולאחורית בקומה 7.

    חזית על הצלע הקצרה: 20×32 = 640 בשש קומות, 14×32 = 448 בשביעית → 4,288.
    חזית על הצלע הארוכה: 22×30 = 660 בשש קומות, 22×24 = 528 בשביעית → 4,488.
    """
    r = _run(box(0, 0, 30, 40), 7)
    assert r.low_sqm == pytest.approx(0.9 * 4288, abs=1)
    assert r.high_sqm == pytest.approx(0.9 * 4488, abs=1)
    assert r.base_sqm == pytest.approx(0.9 * (4288 + 4488) / 2, abs=1)
    assert r.envelope_sqm == pytest.approx(650, abs=1)
    assert r.binding == "envelope"


def test_setbacks_accumulate_from_the_floor_below():
    """‏10–12 מ׳ (8 קומות): 3 מ׳ לקדמית בקומה 7, ועוד 3 בקומה 8 — שם גם לאחורית."""
    assert pe.setbacks(8) == [(1.0, 0.0, 0.0)] * 6 + [(1.0, 3.0, 0.0), (1.0, 6.0, 3.0)]
    assert pe.setbacks(9) == [(1.0, 0.0, 0.0)] * 7 + [(1.0, 3.0, 0.0), (1.0, 6.0, 3.0)]
    # חזית על הצלע הקצרה: 640 × 6 + 17×32 + 11×32
    r = _run(box(0, 0, 30, 40), 8)
    assert r.low_sqm == pytest.approx(0.9 * (640 * 6 + 544 + 352), abs=1)


def test_a_corner_lot_keeps_front_lines_on_two_sides():
    """חזיתות על x0 ו-y0: ‏20 (5+5) × 31 (5+4) = 620, מול 640 בחזית אחת."""
    single = _run(box(0, 0, 30, 40), 6, frontages=1)
    corner = _run(box(0, 0, 30, 40), 6, frontages=2)
    assert corner.corner is True and single.corner is False
    assert corner.high_sqm < single.high_sqm
    assert any("פינתי" in x for x in corner.limits)


def test_five_and_a_half_floors_is_five_floors_and_half_a_plate():
    """קטגוריה נמוכה: עד 6 קומות, קו צד 3.5 מ׳, בלי נסיגות. ‏20×33 = 660 × 5.5."""
    r = _run(box(0, 0, 30, 40), 5.5)
    assert r.low_sqm == pytest.approx(0.9 * 660 * 5.5, abs=1)


def test_never_above_the_cap_and_says_the_cap_binds():
    r = _run(box(0, 0, 30, 40), 7, cap=1000.0)
    assert r.low_sqm == r.base_sqm == r.high_sqm == 1000.0
    assert r.binding == "cap"


def test_more_floors_never_gives_less_area():
    lot = box(0, 0, 40, 60)
    totals = [_run(lot, n).base_sqm for n in (5.5, 7, 8, 9)]
    assert totals == sorted(totals)


def test_unknown_floors_or_geometry_returns_why_and_no_number():
    res, why = pe.compute(box(0, 0, 30, 40), plot_sqm=None, floors_low=None, floors_high=None,
                          cap_400_sqm=8000.0, frontages=1)
    assert res is None and "קומות" in why
    res, why = pe.compute(None, plot_sqm=1200.0, floors_low=7, floors_high=7,
                          cap_400_sqm=8000.0, frontages=1)
    assert res is None and why


def test_unknown_frontages_widen_the_range_downwards():
    known = _run(box(0, 0, 30, 40), 7, frontages=1)
    unknown = _run(box(0, 0, 30, 40), 7, frontages=None)
    assert unknown.low_sqm < known.low_sqm
    assert unknown.base_sqm == pytest.approx(known.base_sqm)
    assert any("פינתי" in a for a in unknown.assumptions)


def test_the_gap_is_against_four_times_the_existing_area_not_the_plot():
    """‏400% בחוק הוא פי ארבעה מהשטח הבנוי הקיים (§70ב). תקרה של 8,000 על מגרש
    של 1,200 היא 667% בנייה, והפער נמדד מול זה — לא מול 400."""
    d = _run(box(0, 0, 30, 40), 7, cap=8000.0).as_dict()
    assert d["cap_400_far_pct"] == pytest.approx(666.7, abs=0.1)
    base = d["base"]
    assert base["far_pct"] == pytest.approx(base["sqm"] / 1200 * 100, abs=0.1)
    assert base["gap_far_pct"] == pytest.approx(666.7 - base["far_pct"], abs=0.2)
    assert base["gap_sqm"] == pytest.approx(8000 - base["sqm"], abs=0.2)
    assert base["unrealizable_share"] == pytest.approx(1 - base["sqm"] / 8000, abs=0.001)
    assert d["certainty"] == "estimate" and d["sources"][0]["url"]


def test_a_rotated_lot_gives_the_same_area_as_an_upright_one():
    from shapely import affinity
    upright = _run(box(0, 0, 30, 40), 8)
    turned = _run(affinity.rotate(box(0, 0, 30, 40), 33, origin="centroid"), 8)
    assert turned.base_sqm == pytest.approx(upright.base_sqm, rel=0.01)


# אלוף יגאל אלון 40 (6537/120), הפוליגון הקדסטרלי ב-ITM. ‏#78 מצא 51%–64% מהתקרה
# (η=0.9) ב-7–9 קומות; התקרה 11,301 מ״ר.
ALON_40 = MultiPolygon([Polygon([
    (185988.84, 675037.0), (185964.05, 675038.06), (185949.83, 675038.62),
    (185959.05, 675083.04), (185976.29, 675082.15), (185989.14, 675084.84),
    (185988.84, 675037.0)])])


def test_a_demo_parcel_lands_where_the_research_put_it():
    r = _run(ALON_40, 7, 9, cap=11_300.8, frontages=1, plot=1575.0)
    d = r.as_dict()
    assert d["low"]["share_of_cap"] == pytest.approx(0.51, abs=0.03)
    assert d["high"]["share_of_cap"] == pytest.approx(0.64, abs=0.04)
    assert 0.5 < d["envelope_share_of_plot"] < 0.7
