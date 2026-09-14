"""שרשרת הזכויות. הבדיקות מכוונות למקומות שקל לטעות בהם, לא לכיסוי."""
import pytest

from app.cities.herzliya import rights as R


# ── §70א · תנאי הסף ──

def test_the_definition_itself_is_the_threshold_not_only_its_numbered_items():
    """הבדיקה הזו קבעה פעם ש-§70א מונה ארבעה שערים ו״שטח בנוי אינו אחד מהם״.
    זו הייתה קריאה של הסעיפים הממוספרים בלבד. גוף ההגדרה מוסיף שניים —
    ייעוד למגורים, ו-70% מהשטח הבנוי המשמש למגורים — והשני הוא דווקא כן
    מבחן על שטח בנוי. המדיניות מפורשת: ״תנאי סף... הינו עמידה בהגדרות
    סעיף 70א״, ההגדרה כולה."""
    ids = {c.id for c in R.threshold_checks({"permit_date": "1978-01-01", "strengthened": False,
                                             "floors": 4, "units": 32})}
    assert {"residential_zoning", "residential_share",
            "permit_date", "strengthened", "floors", "units"} <= ids
    # אומדן השטח הקיים עדיין אינו שער: הוא נכנס ב-§70ב, בחישוב התקרה.
    assert not {"existing_area", "parcel_area", "street_width"} & ids


def test_the_seventy_percent_test_is_unknown_rather_than_assumed_to_pass():
    """אין מקור פתוח לחלק המשמש למגורים. ״לא ידוע״ מוריד את הסטטוס
    ל-needs_verification; ״עבר״ היה מוכר בניין שאיש לא בדק."""
    def status(d, i="residential_share"):
        return next(c.status for c in R.threshold_checks(d) if c.id == i)
    assert status({}) == "unknown"
    assert status({"residential_share": 0.69}) == "failed"
    assert status({"residential_share": 0.70}) == "passed"


def test_a_plot_not_designated_for_housing_fails_rather_than_waits():
    def status(d):
        return next(c.status for c in R.threshold_checks(d) if c.id == "residential_zoning")
    assert status({"residential_zoning": True}) == "passed"
    assert status({"residential_zoning": False}) == "failed"
    assert status({}) == "unknown"


def test_the_floor_count_carries_the_caveat_that_70a3_counting_was_not_applied():
    """§70א(3) סופר קומת עמודים וגורע קומה עליונה קטנה מחצי. ‏Num_floors
    העירוני הוא ספירה פיזית. הערך נמסר — עם הסייג, לא בשתיקה."""
    detail = next(c.detail for c in R.threshold_checks({"floors": 4}) if c.id == "floors")
    assert "§70א(3)" in detail


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

def test_every_boundary_of_the_street_table():
    """כל גבול בטבלה, ולא דגימה. הקודם החזיר ״לא מוגדר״ ב-9.0 בדיוק, בעוד
    שהמדיניות כותבת ״9-10 מ׳״ — כלומר 9.0 שייך לשורה ומקבל 7 קומות."""
    assert R.floors_for_width(8.0) is None          # "עד 8 מ' כולל"
    assert R.floors_for_width(8.01) == "undefined"  # הפער שאינו בטבלה
    assert R.floors_for_width(8.99) == "undefined"
    assert R.floors_for_width(9.0) == 7             # ← הגבול שהיה שגוי
    assert R.floors_for_width(10.0) == 7
    assert R.floors_for_width(10.01) == 8
    assert R.floors_for_width(12.0) == 8
    assert R.floors_for_width(12.01) == 9
    assert R.floors_for_width(15.0) == 9
    assert R.floors_for_width(15.01) == R.UNBOUND   # הרחוב מפסיק להגביל
    assert R.floors_for_width(None) == "unknown"


def test_a_band_spanning_two_floor_counts_is_never_reported_certain():
    """‏11.0 ± 1 חוצה את גבול ה-12 מ׳ ולכן 7–8. לדווח אותו כוודאי זה בדיוק
    מה שתחום הסבילות נועד למנוע."""
    r = R.floors(11.0, CAT)
    assert (r.floors_low, r.floors_high) == (7, 8)
    assert r.floors_certain is False
    # ‏`needs_measurement` ולא `undefined`: המדיניות מכסה את 11.0 מ׳ היטב,
    # והמדידה שלנו היא זו שחוצה שורה. ״לא מוגדר״ היה שולח את הקורא לחפש
    # בעיה במדיניות במקום לצאת למדוד את הרחוב.
    check = next(c for c in r.checks if c.id == "street_width")
    assert check.status == "needs_measurement"
    assert "מדידה בשטח תכריע" in check.detail


def test_the_policy_gap_and_our_measurement_are_told_apart():
    """‏8-9 מ׳ הוא חור אמיתי בטבלה; ‏11.5 מ׳ הוא שורה ברורה שהמדידה שלנו
    מטשטשת. שתי מסקנות הפוכות לגבי מה לעשות הלאה, ובגרסה הקודמת שתיהן
    חזרו כ-`undefined`."""
    def status(w):
        return next(c.status for c in R.floors(w, CAT).checks if c.id == "street_width")
    assert status(8.5) == "undefined"            # המדיניות שותקת
    assert status(11.5) == "needs_measurement"   # אנחנו לא מדדנו מספיק טוב
    assert status(20.0) == "needs_measurement"   # מדידת פער רחבה אינה מוכיחה רחוב רחב


def test_the_category_ceiling_caps_the_street_table():
    """קטגוריה נמוכה חוסמת מתחת לכל שורה בטבלה — 5.5 ולא 9."""
    r = R.floors(14.0, "התחדשות מגרשית מוטת מגורים נמוכה")
    assert r.floors_high == 5.5

CAT = "התחדשות מגרשית מוטת מגורים"


def test_the_narrow_end_of_the_band_counts_not_just_the_centre():
    r = R.floors(9.4, CAT)
    assert (r.floors_low, r.floors_high) == (7, 8)
    assert not r.floors_certain          # התחום נוגע בפער 8–9

def test_the_policy_still_stops_binding_above_fifteen_metres():
    """הטבלה עצמה לא השתנתה: רחוב שרוחבו באמת מעל 15 מ׳ אינו מגביל."""
    assert R.floors_for_width(33.0) == R.UNBOUND


def test_a_wide_gap_measurement_does_not_lift_the_street_limit():
    """הבדיקה הזו קבעה פעם ש-33 מ׳ הם ״9 קומות, ודאי, בחינה נקודתית״.
    ארלוזורוב 5 קיבלה 33.0 לחזית שווידלסון, ובמדידה ידנית החזית 10.4 מ׳ —
    8 קומות. מעל RELIABLE_MAX_M הערך הוא חסם עליון, לא מדידה."""
    r = R.floors(33.0, CAT)
    assert (r.floors_low, r.floors_high) == (7, 9)
    assert not r.floors_certain
    assert not r.case_by_case        # ״נקודתית״ הסתירה את ״דורש מדידה״ במסכים
    check = next(c for c in r.checks if c.id == "street_width")
    assert check.status == "needs_measurement"
    assert "מדידה בשטח תכריע" in check.detail


# מנוע מול מדידה ידנית ב-GovMap של אותה חזית, חציון שלוש נקודות.
# מקור: POC/layer_a/validation/street_width.csv ו-d1_followup.json (14.09.2026).
MEASURED = [
    (9.0, 8.2), (9.0, 9.7), (9.0, 8.92), (10.0, 10.5), (10.0, 10.0), (10.0, 10.0),
    (10.2, 10.2), (11.8, 11.3), (12.1, 11.5), (14.0, 10.8), (14.9, 14.98),
    (17.3, 16.0), (20.6, 11.3), (29.1, 9.9), (31.7, 16.7), (33.0, 10.4), (37.2, 18.3),
]


@pytest.mark.parametrize("engine,measured", MEASURED)
def test_the_reported_range_holds_for_every_street_measured_by_hand(engine, measured):
    """לכל רחוב שנמדד ביד: אם המדיניות נותנת לו מספר, הטווח שהמנוע מדווח
    מכיל אותו. אם לא — המנוע לא מדווח ודאות."""
    r = R.floors(engine, CAT)
    truth = R.floors_for_width(measured)
    status = next(c.status for c in r.checks if c.id == "street_width")
    if truth in (None, "undefined"):
        assert status != "passed"
    else:
        truth = min(truth, 9.0)
        assert r.floors_low <= truth <= r.floors_high

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


# ── §70ב(א)(1)(ב) · ההחרגה שאחרי 18.5.2005 ──

def test_a_post_2005_addition_leaves_the_four_hundred_percent_base():
    """התקרה מוכפלת פי ארבע, ולכן כל מ״ר שנשאר בבסיס בטעות שווה ארבעה."""
    assert R.cap_400(2000.0, 200.0)[0] == 7200.0
    assert R.cap_400(2000.0, False)[0] == 8000.0


def test_not_checked_and_checked_and_none_do_not_look_alike():
    """שניהם נראים כמו אפס אם שואלים רק כן/לא, והאחד הוא ממצא והשני חוסר."""
    assert "לא נבדק" in R.cap_400(2000.0, None)[1]
    assert "לא נבדק" not in R.cap_400(2000.0, False)[1]
    assert "אינו ידוע" in R.cap_400(2000.0, True)[1]
    assert [R.cap_400_reliable(v) for v in (None, True, False, 200.0)] == [False, False, True, True]


def test_a_boolean_is_never_mistaken_for_an_area():
    """‏`True` הוא 1 בפייתון. אם ההחרגה נקראת כשטח, התקרה יורדת בארבעה מ״ר
    בשקט ונראית כאילו נבדקה."""
    assert R.cap_400(2000.0, True)[0] == 8000.0


# ── שלב 6 · הפרשה ──

def test_allocation_on_the_ceiling_says_so_in_the_reason():
    """המדיניות מחשבת 10% מ״סך השטחים בתכנית לאחר ההגדלה״. תקרת 400% אינה
    זה — היא החסם שהתכנית מותרת להגיע אליו."""
    assert "חסם עליון" in R.allocation(8000.0, "שז\"ר", total_is_ceiling=True)[1]
    assert "חסם עליון" not in R.allocation(8000.0, "שז\"ר")[1]


def test_an_area_outside_the_policy_lists_gets_no_invented_floor():
    assert R.allocation(8000.0, "בית ספר ירוק")[0] is None


# ── שלב 9 · חניה ──

def test_guest_parking_is_a_share_of_all_units_not_of_the_small_ones():
    """״ידרשו 20% ממספר יח״ד״. הגרסה הקודמת חישבה 20% מהדירות הקטנות."""
    p = R.parking(20, False, [25.0] * 10 + [50.0] * 10)
    assert p["guests"] == 4.0                      # 20% מ-20, לא מ-10


def test_guest_parking_does_not_apply_where_the_standard_exceeds_one_to_one():
    """הסעיף מותנה ב״תבע״ות שבהם תקן החניה 0-1:1״."""
    assert R.parking(20, False, [90.0] * 20)["guests"] == 0.0


def test_accessible_basement_spaces_count_only_the_units_under_thirty_metres():
    """״חניות נגישות בשיעור של 10% ממספר יח״ד ששטחן עד 30 מ״ר״ — ולא מכולן."""
    p = R.parking(20, False, [25.0] * 10 + [50.0] * 10)
    assert p["accessible_basement"] == 1.0


def test_the_small_flat_bands_are_priced_at_their_own_rates():
    p = R.parking(3, False, [30.0, 65.0, 66.0])
    assert p["spaces"] == 2.5                      # 0 + 1.0 + 1.5, הגבולות כולל


def test_zero_units_does_not_divide_by_zero():
    assert R.parking(0, False, [])["per_unit"] is None


# ── שלב 8 · תמהיל ──

def test_the_unit_multiplier_is_the_current_policy_band():
    """‏2.8–3.18 מהמדיניות התקפה. ‏32 לדונם הוא נוסח ועדה 769 שהוחלף, ואסור
    שיחזור לכאן דרך הדלת האחורית."""
    m = R.unit_mix(20)
    assert (m["units_min"], m["units_max"]) == (56, 64)


def test_a_quarter_of_the_units_must_be_small_and_a_tenth_of_those_micro():
    m = R.unit_mix(20)
    assert m["small_min"] == 16 and m["micro_max"] == 2 and m["accessible"] == 6


def test_the_mix_is_infeasible_when_the_average_flat_falls_below_the_small_band():
    assert R.unit_mix(20, sellable_main=3000.0)["mix_feasible"] is False   # 46.9 מ"ר
    assert R.unit_mix(20, sellable_main=4000.0)["mix_feasible"] is True    # 62.5 מ"ר


def test_the_gis_name_for_the_green_area_reaches_the_policy_floor():
    """‏**שם אחד, שתי מערכות, ושלוש חלקות שאיבדו זכות.**

    מסמך המדיניות קורא לאזור ״הירוק״; שכבת ה-GIS קוראת לו ״בית ספר
    ירוק (שם זמני)״. ההשוואה הייתה מחרוזת מדויקת, ולכן `allocation()`
    החזיר ״אינו ברשימות הרצפה״ — ושלוש חלקות יצאו בלי רצפת ההפרשה
    לשב״צ, כלומר **נראו רווחיות יותר משהן**.

    נמצא בביקורת הלילית של 14.09.2026.
    """
    from app.cities.herzliya import rights

    gis, policy = "בית ספר ירוק (שם זמני)", "הירוק"
    assert rights.canonical_area(gis) == policy
    assert policy in rights.ALLOCATION_FLOOR_400

    same = rights.allocation(10_000.0, gis)
    as_policy = rights.allocation(10_000.0, policy)
    assert same == as_policy, "שני השמות חייבים להחזיר את אותה הפרשה"
    assert same[0] == 1_000.0                       # ‏10% ≥ רצפת 400


def test_an_unknown_registration_area_says_so_and_allocates_nothing():
    """אזור שאינו מוכר אינו מקבל רצפה בשקט — הוא אומר את שמו בנימוק,
    כדי שהשם החדש ייראה בתיק ויגיע לאדם שיחליט אם למפות אותו."""
    from app.cities.herzliya import rights

    area, why = rights.allocation(10_000.0, "שכונה שאינה במדיניות")
    assert area is None
    assert "שכונה שאינה במדיניות" in why
