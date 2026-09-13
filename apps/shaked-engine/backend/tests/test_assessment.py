"""ההערכה שנשמרת על ההזדמנות, ומה שבמכוון אינו נכתב לתוך verification_level."""
from app.cities.herzliya.assessments import DELIVERABLE
from app.models.opportunity import VerificationLevel


def test_a_compound_routed_candidate_is_not_deliverable():
    """שלושה מבנים ומעלה מנותבים למסלול מתחמים, שכללי הזכויות שלו אחרים.
    זה ניתוב ולא פסילה — אבל הוא גם לא נמסר במסלול המגרשי."""
    assert "urban_renewal_compound" not in DELIVERABLE
    assert "ineligible" not in DELIVERABLE
    assert DELIVERABLE == {"eligible", "needs_verification"}


def test_verification_level_describes_provenance_not_confidence():
    """‏A11 נוסחה כ״שכבת ביטחון → verification_level״, וזו הייתה הנחה שגויה.
    האנום מתאר איך נתון הושג, לא כמה בטוח חישוב הזכויות. אין בו ערך
    שמשמעותו ״ודאות גבוהה״, ולכן כתיבת ביטחון לתוכו היא טעות קטגורית."""
    values = {v.value for v in VerificationLevel}
    assert values == {"raw", "ocr_extracted", "ai_assisted", "human_verified"}
    assert not {"certain", "tier_0", "high_confidence"} & values
