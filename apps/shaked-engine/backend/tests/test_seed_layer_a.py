"""זריעת שכבה א׳: שהשדות נושאים מקור, ושה-category אינו נדרס.

הבדיקה השנייה קיימת בגלל תקלה אמיתית: `metadata_json["category"]` הוא
קטגוריית הסינון של ה-engine, ובזריעה הראשונה נכתבה לשם קטגוריית מפת
המדיניות. כל 699 השורות נעלמו מ-`screen_herzliya_candidates` **בלי שגיאה**,
כי הן פשוט לא ענו על הפילטר. זה נראה כמו בסיס נתונים ריק.
"""
import pytest

from app.cities.herzliya.seed_layer_a import CATEGORY, _metadata, _rows, _load
from app.cities.herzliya.xplan_schema import QUEUE_ELIGIBLE_CATEGORIES
from app.evidence import Certainty

SURV = {"lot": 1816, "apt": 28, "floors": 4, "cat": "9", "entrances": 2, "pilotis": False}


def test_category_is_the_engines_screening_vocabulary_not_the_policy_map():
    m = _metadata("6537/222", SURV, {"width": 15.5})
    assert m["category"] in QUEUE_ELIGIBLE_CATEGORIES
    assert m["renewal_policy_category"] in CATEGORY.values()
    assert m["category"] != m["renewal_policy_category"]


def test_unmeasured_street_is_needs_verification_not_primary():
    assert _metadata("x/1", SURV, {})["category"] == "needs_verification"
    assert _metadata("x/1", SURV, {"width": 12.0})["category"] == "primary_candidate"


def test_every_evidence_row_carries_a_source_and_a_location():
    sources = _load("source_fetched.json")
    rows = _rows("6537/222", SURV, {"width": 15.5, "why": "x"}, {}, sources, [])
    assert rows
    for r in rows:
        assert r["source_url"].startswith("https://"), r["field"]
        assert r["retrieved_at"], r["field"]
        assert r["location"], r["field"]
        assert r["certainty"] in {c.value for c in Certainty}


def test_a_field_without_a_known_source_is_not_written_at_all():
    rows = _rows("6537/222", SURV, {"width": 15.5}, {}, {}, [])
    assert rows == []


def test_policy_categories_match_the_plans_wording():
    # עמ' 8 בהר/2323: שתיהן "מגרשית". "עירונית" אינו מופיע שם.
    assert all("מגרשית" in v for v in CATEGORY.values())
