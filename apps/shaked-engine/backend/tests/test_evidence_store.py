"""נתיב הקריאה של הראיות — הצד שאיש לא בדק עד A9.

‏`usable()` ו-`resolve_evidence()` היו קיימות ונכונות, אבל שום דבר לא קרא
שורות `FieldEvidence` בחזרה, ולכן בדיקת הגיל וזיהוי הסתירה מעולם לא פעלו
על נתון אמיתי. הבדיקות כאן מפעילות אותן.
"""
from datetime import datetime, timedelta, timezone

from app.evidence import Certainty, evidence, resolve_evidence, usable

NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _field(days_old=1, certainty=Certainty.OFFICIAL, value=2265, location="גוש 6424 חלקה 144"):
    return evidence(value,
                    source={"url": "https://open.govmap.gov.il/x",
                            "retrieved_at": (NOW - timedelta(days=days_old)).isoformat()},
                    certainty=certainty, location=location)


def test_a_fresh_official_field_decides():
    assert usable(_field(1), now=NOW)


def test_the_thirty_first_day_stops_it_deciding():
    assert usable(_field(29), now=NOW)
    assert not usable(_field(31), now=NOW)


def test_a_field_without_a_location_never_decides():
    assert not usable(_field(location=None), now=NOW)


def test_an_ocr_reading_never_decides_however_fresh():
    assert not usable(_field(0, Certainty.OCR_CANDIDATE), now=NOW)
    assert not usable(_field(0, Certainty.COMMUNITY), now=NOW)


def test_two_sources_that_disagree_become_a_conflict_and_decide_nothing():
    r = resolve_evidence([_field(value=2265), _field(value=2300)])
    assert r["certainty"] == "conflict"
    assert len(r["observations"]) == 2     # שתיהן נשמרות, אף אחת לא נדרסת
    assert not usable(r, now=NOW)


def test_two_sources_that_agree_keep_the_value():
    r = resolve_evidence([_field(value=2265), _field(value=2265)])
    assert r["value"] == 2265
    assert usable(r, now=NOW)
