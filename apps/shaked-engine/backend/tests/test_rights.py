"""שרשרת הזכויות. הבדיקות מכוונות למקומות שקל לטעות בהם, לא לכיסוי."""
import pytest

from app.cities.herzliya import rights as R


# ── §70א · תנאי הסף ──

def test_built_area_is_not_a_threshold_condition():
    """§70א מונה מועד היתר, חיזוק, קומות ודירות. שטח בנוי אינו אחד מהם,
    ולכן אומדן שטח לעולם אינו יכול לפסול חלקה."""
    ids = {c.id for c in R.threshold_checks({"permit_date": "1978-01-01", "strengthened": False,
                                             "floors": 4, "units": 32})}
    assert "existing_area" not in ids
    # ארבעת השערים של §70א עצמו. `occupied` אינו אחד מהם — הוא שער זמינות
    # מסחרית ולא תנאי סף בחוק — אבל הוא כן נבדק באותו מעבר.
    assert {"permit_date", "strengthened", "floors", "units"} <= ids
    assert not {"existing_area", "parcel_area", "street_width"} & ids


def test_1980_to_1984_needs_an_engineers_opinion():
    def status(d):
        return next(c.status for c in R.threshold_checks(d) if c.id == "permit_date")
    assert status({"permit_date": "1979-12-31"}) == "passed"
    assert status({"permit_date": "1982-01-01"}) == "unknown"          # אין חוות דעת
    assert status({"permit_date": "1982-01-01", "engineer_opinion": True}) == "passed"
    assert status({"permit_date": "1985-01-01"}) == "failed"


def test_an_unknown_permit_date_is_not_a_pass():
    assert next(c.status for c in R.threshold_checks({}) if c.id == "permit_date") == "unknown"


# ── שלב 4 · הרחוב ──

CAT = "התחדשות מגרשית מוטת מגורים"


def test_the_narrow_end_of_the_band_counts_not_just_the_centre():
    r = R.floors(9.4, CAT)
    assert (r.floors_low, r.floors_high) == (7, 8)
    assert not r.floors_certain          # התחום נוגע בפער 8–9

def test_above_fifteen_metres_the_street_stops_binding():
    r = R.floors(33.0, CAT)
    assert r.floors_low == r.floors_high == 9.0     # תקרת הקטגוריה
    assert r.case_by_case

def test_the_low_category_binds_below_every_row_of_the_street_table():
    r = R.floors(20.0, "התחדשות מגרשית מוטת מגורים נמוכה")
    assert r.floors_high == 5.5

def test_eight_metres_or_less_is_no_addition_at_all():
    assert R.floors(7.0, CAT).floors_low is None

def test_an_unmeasured_width_cannot_reduce_the_ceiling():
    r = R.floors(None, CAT)
    assert r.floors_low is None
    assert any(c.id == "street_width" and c.status == "unknown" for c in r.checks)


# ── שלבים 6–9 ──

def test_balconies_add_rather_than_deduct():
    area, _ = R.balconies(102)
    assert area == 1224.0

def test_allocation_below_the_floor_is_not_required():
    assert R.allocation(2000, "בן צבי")[0] == 0.0      # 10% = 200 < 400
    assert R.allocation(8534, "בן צבי")[0] == pytest.approx(853.4)

def test_parking_refuses_to_guess_whether_the_parcel_is_inside_tama_70():
    assert R.parking(100, None)["spaces"] is None
    assert R.parking(100, True)["spaces"] == 100.0
    assert R.parking(100, False)["spaces"] == 150.0


def test_a_main_axis_with_an_alternative_frontage_is_not_flagged():
    assert R.main_axis_only(["סוקולוב", "הגליל"]) is None
    assert R.main_axis_only(["סוקולוב"]) is not None


def test_the_four_hundred_percent_cap_includes_service_area():
    cap, why = R.cap_400(2133.0)
    assert cap == 8532.0
    assert "שירות" in why
