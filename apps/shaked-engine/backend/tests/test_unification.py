"""איחוד מגרשים — והשאלה שהבדיקה הקודמת לא שאלה.

התנאי נוסח כ״אף חלקה אינה מבודדת״, וזה אינו קשירוּת. שני זוגות צמודים
במרחק קילומטר זה מזה מקיימים אותו: כל חלקה נוגעת בחלקה אחרת בקבוצה,
הבדיקה עברה, והשטחים חוברו למגרש אחד שעובר את הסף העירוני. שום שדה
בתשובה לא אמר שהם אינם רצופים.
"""
import pytest

from app.cities.herzliya.rules import HERZLIYA_MINIMUM_PLOT_AREA_SQM, HerzliyaCityRules
from app.models.opportunity import Opportunity, VerificationLevel


def _square(lon, lat, w=0.0008, h=0.0006):
    """ריבוע ~74×66 מ׳, כלומר כ-4,900 מ״ר — מעל הסף העירוני לבדו."""
    pts = [(lon, lat), (lon + w, lat), (lon + w, lat + h), (lon, lat + h), (lon, lat)]
    return "MULTIPOLYGON(((" + ",".join(f"{x:.7f} {y:.7f}" for x, y in pts) + ")))"


async def _parcel(session, block, lon, lat):
    opp = Opportunity(city_code="herzliya", address=f"רחוב הבדיקה {block}",
                      block=block, block_suffix=0, parcel="1",
                      geom=f"SRID=4326;{_square(lon, lat)}",
                      verification_level=VerificationLevel.RAW.value, metadata_json={})
    session.add(opp)
    await session.flush()
    return str(opp.id)


@pytest.mark.asyncio
async def test_two_parcels_sharing_an_edge_unify(session):
    a = await _parcel(session, "9101", 34.8400, 32.1600)
    b = await _parcel(session, "9102", 34.8408, 32.1600)      # הגבול המשותף
    r = await HerzliyaCityRules().check_plot_unification(session, [a, b])
    assert r.is_unifiable, r.reason
    assert r.combined_area_sqm > HERZLIYA_MINIMUM_PLOT_AREA_SQM


@pytest.mark.asyncio
async def test_two_touching_pairs_a_kilometre_apart_are_refused(session):
    """המקרה שעבר קודם. השטח המאוחד עובר את הסף — וזה בדיוק מה שמסוכן בו."""
    a = await _parcel(session, "9103", 34.8400, 32.1600)
    b = await _parcel(session, "9104", 34.8408, 32.1600)
    c = await _parcel(session, "9105", 34.8500, 32.1700)      # ~1.3 ק״מ משם
    d = await _parcel(session, "9106", 34.8508, 32.1700)
    r = await HerzliyaCityRules().check_plot_unification(session, [a, b, c, d])
    assert not r.is_unifiable
    assert "contiguous" in r.reason


@pytest.mark.asyncio
async def test_a_parcel_that_touches_nothing_is_still_refused(session):
    a = await _parcel(session, "9107", 34.8400, 32.1600)
    far = await _parcel(session, "9108", 34.8600, 32.1800)
    r = await HerzliyaCityRules().check_plot_unification(session, [a, far])
    assert not r.is_unifiable


@pytest.mark.asyncio
async def test_a_contiguous_set_below_the_minimum_is_refused_on_area_not_on_shape(session):
    a = await _parcel(session, "9109", 34.8400, 32.1600)
    b = await _parcel(session, "9110", 34.8400 + 0.0001, 32.1600)
    # שתי החלקות חופפות, ולכן האיחוד קשיר; השטח הוא זה שנבדק אחריו.
    r = await HerzliyaCityRules().check_plot_unification(session, [a, b])
    assert r.is_unifiable or "minimum" in r.reason


@pytest.mark.asyncio
async def test_one_parcel_is_not_a_unification(session):
    a = await _parcel(session, "9111", 34.8400, 32.1600)
    r = await HerzliyaCityRules().check_plot_unification(session, [a])
    assert not r.is_unifiable and "two parcels" in r.reason
