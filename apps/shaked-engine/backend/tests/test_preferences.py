"""מיון לפי סדר ההעדפות של היזם, והנימוק לכל בחירה — PRD 4.2 · SEL-01.

‏״לא נדרש ציון משוקלל סמוי כדי לבחור שלוש תוצאות״: הסדר הוא לקסיקוגרפי
לפי מה שהיזם הגדיר, וכל תוצאה אומרת איזו העדפה הציבה אותה.
"""
from app.cities.herzliya.candidates import SORTABLE, _value, _why_selected


def row(addr, area, units, floors=None):
    return {"address": addr, "area_sqm": area, "existing_units": units,
            "assessment": {"floors_low": floors, "cap_400_sqm": None}}


AREA = [{"field": "parcel_area", "direction": "desc"}]
UNITS_THEN_AREA = [{"field": "units", "direction": "desc"},
                   {"field": "parcel_area", "direction": "desc"}]


def test_the_first_preference_explains_the_placement():
    rows = [row("א", 3608, 48), row("ב", 2366, 32)]
    _why_selected(rows, AREA)
    assert "שטח המגרש" in rows[0]["why_selected"]
    assert "3,608" in rows[0]["why_selected"] and "2,366" in rows[0]["why_selected"]


def test_a_tie_on_the_first_preference_is_explained_by_the_second():
    """שתי חלקות עם אותו מספר דירות — ההעדפה השנייה היא שהכריעה, והנימוק
    חייב לומר אותה ולא את הראשונה."""
    rows = [row("א", 2366, 32), row("ב", 433, 32)]
    _why_selected(rows, UNITS_THEN_AREA)
    assert "שטח המגרש" in rows[0]["why_selected"]
    assert "מספר הדירות" not in rows[0]["why_selected"]


def test_the_last_row_has_no_one_to_be_compared_against():
    rows = [row("א", 3608, 48), row("ב", 2366, 32)]
    _why_selected(rows, AREA)
    assert "מול" not in rows[-1]["why_selected"]
    assert "2,366" in rows[-1]["why_selected"]


def test_identical_on_every_preference_says_so_rather_than_inventing_a_reason():
    rows = [row("א", 1000, 10), row("ב", 1000, 10)]
    _why_selected(rows, UNITS_THEN_AREA)
    assert "מזהה יציב" in rows[0]["why_selected"]


def test_no_preferences_is_stated_and_not_disguised_as_ranking():
    rows = [row("א", 1000, 10)]
    _why_selected(rows, [])
    assert "לא הוגדרו העדפות" in rows[0]["why_selected"]


def test_every_sortable_field_can_actually_be_read_from_a_row():
    """שדה שניתן למיין לפיו אך לא לקרוא אותו היה מייצר נימוק ריק בשקט."""
    r = row("א", 1000, 10, floors=9)
    assert _value(r, "parcel_area") == 1000
    assert _value(r, "units") == 10
    assert _value(r, "floors") == 9
    for field in SORTABLE:
        assert _value(r, field) is not None or field == "cap_400"


# ── תנאי חובה, שהם דבר אחר מהעדפות ──

def test_mandatory_and_sortable_are_not_the_same_list():
    """‏SEL-01 מונה ״כללים, תנאי חובה וסדר העדיפויות״ כשלושה דברים. תנאי
    חובה מוציא מועמד מהרשימה; העדפה רק מזיזה אותו בה. מינימום שנשלח
    כהעדפה היה מדרג נמוך מועמד שהיזם כלל אינו רוצה לראות."""
    from app.cities.herzliya.candidates import MANDATORY, SORTABLE
    assert set(MANDATORY) == {"min_area_sqm", "min_units", "min_floors", "min_cap_400_sqm"}
    assert not set(MANDATORY) & set(SORTABLE)


def test_every_mandatory_condition_has_a_hebrew_label():
    """הן מוצגות ליזם, ולא רק נשלחות."""
    from app.cities.herzliya.candidates import MANDATORY
    assert all(label and not label.isascii() for _, label in MANDATORY.values())
