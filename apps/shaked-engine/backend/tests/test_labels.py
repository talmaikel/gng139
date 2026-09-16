"""‏A8 · אין מזהה קוד שמגיע למסך של היזם.

הבדיקה הזו נכתבה אחרי שהתגלה שהמסך הציג ליזם `betterment_levy_rate`
במקום ״שיעור היטל ההשבחה״ — לא בגלל באג, אלא בגלל **מפת תוויות כפולה**:
אחת בשרת ואחת ב-`frontend/src/lib/labels.ts`. השדה שונה בשרת, המפה
בדפדפן לא, ושום דבר לא נצבע באדום. מפה כפולה נושרת בשקט; בדיקה לא.
"""
import re

import pytest

from app.cities.herzliya import rights
from app.cities.herzliya.dossier import (
    ASSUMPTION_LABEL, CERTAINTY_LABEL, FIELD_LABEL, _not_delivered,
)
from app.models.evidence import Certainty
from app.services.economic.assumptions import HERZLIYA_2026_V2 as A

# מזהה קוד: רצף אותיות לטיניות קטנות עם קו תחתון. עברית עוברת, מספרים
# ויחידות (₪, מ״ר) עוברים, ו-`sale_price_per_sqm_ils` נתפס.
IDENTIFIER = re.compile(r"[a-z]{3,}_[a-z_]{3,}")


def test_every_assumption_has_a_hebrew_label():
    """הנחה חדשה בלי תווית נופלת כאן, ולא מודפסת ליזם כמזהה."""
    unlabelled = sorted(set(A.report()) - set(ASSUMPTION_LABEL))
    assert not unlabelled, f"הנחות בלי תווית: {unlabelled}"


def test_no_orphan_assumption_labels():
    """תווית ששרדה שינוי שם מצביעה על שדה שכבר אינו קיים — והיא לעולם
    לא תוצג. ‏`betterment_levy_ratio` שרד כך שבוע שלם."""
    orphans = sorted(set(ASSUMPTION_LABEL) - set(A.report()))
    assert not orphans, f"תוויות יתומות: {orphans}"


def test_every_threshold_field_has_a_label():
    unlabelled = sorted(set(rights.THRESHOLD_IDS) - set(FIELD_LABEL))
    assert not unlabelled, f"שערי סף בלי תווית: {unlabelled}"


def test_every_certainty_level_has_a_label():
    unlabelled = sorted({c.value for c in Certainty} - set(CERTAINTY_LABEL))
    assert not unlabelled, f"רמות ודאות בלי תווית: {unlabelled}"


@pytest.mark.parametrize("label", sorted(ASSUMPTION_LABEL.values())
                                 + sorted(FIELD_LABEL.values())
                                 + sorted(CERTAINTY_LABEL.values()))
def test_labels_are_not_identifiers(label):
    assert not IDENTIFIER.search(label), f"מזהה קוד בתוך תווית: {label!r}"


def test_the_sentence_the_developer_reads_carries_no_identifier():
    """המשפט היחיד שמסביר ליזם למה אין תרחיש — שלוש פעמים הוא הודפס עם
    מזהים גולמיים (PDF, Excel, מסך). עכשיו הוא נכתב פעם אחת ונבדק."""
    sentence = _not_delivered(A.blocking())
    assert sentence, "יש הנחות חסרות, ולכן חייב להיות משפט"
    assert not IDENTIFIER.search(sentence), sentence
    for k in A.blocking():
        assert ASSUMPTION_LABEL[k] in sentence


def test_no_sentence_when_nothing_is_missing():
    assert _not_delivered([]) is None
