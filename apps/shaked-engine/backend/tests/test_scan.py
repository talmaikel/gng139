"""‏S1 · סריקה: פוליגון → עד שלושה תיקים, בלי לחשוף מועמדים.

בועז, 15.09: הלקוח אינו רואה מועמדים. הוא מצייר אזור, רואה *״נמצאו N —
לקבל?״*, ומקבל עד שלושה תיקים לפי התנאים וההעדפות שלו — מוכנים קודם.
הבדיקות כאן על שני דברים שנכשלים בשקט: **דליפה** של מגרש שלא נמסר, ו**חיוב**
על מה שלא נמסר.
"""
import json

import pytest
from sqlalchemy import select

from app.api.v1 import candidates as api
from app.cities.herzliya.archive_facts import ArchiveUnavailable
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.package import Balance
from tests.test_api import client  # noqa: F401 — הפיקסטורה

# אזור בתוך הגבול העירוני שאין בו מגרשים זרועים — הספירות כאן דטרמיניסטיות.
AREA = {"type": "Polygon", "coordinates": [[[34.8100, 32.1600], [34.8120, 32.1600],
                                            [34.8120, 32.1615], [34.8100, 32.1615],
                                            [34.8100, 32.1600]]]}
BY_CAP = {"polygon": AREA, "preferences": [{"field": "cap_400", "direction": "desc"}]}


async def _parcel(session, block, cap, ready=True):
    geom = ("MULTIPOLYGON(((34.8105000 32.1605000,34.8109000 32.1605000,"
            "34.8109000 32.1608000,34.8105000 32.1608000,34.8105000 32.1605000)))")
    opp = Opportunity(city_code="herzliya", address=f"רחוב הסריקה {block}", block=block,
                      block_suffix=0, parcel="1", geom=f"SRID=4326;{geom}",
                      area_sqm=1000.0, existing_units=12,
                      verification_level=VerificationLevel.RAW.value,
                      metadata_json={"category": "primary_candidate",
                                     "assessment": {"status": "needs_verification",
                                                    "screenable": True, "deliverable": ready,
                                                    "floors_low": 8, "cap_400_sqm": cap}})
    session.add(opp)
    await session.flush()
    return opp


async def _credits(session, company_id, n):
    session.add(Balance(company_id=company_id, credits_remaining=n))
    await session.flush()


async def _balance(session, company_id):
    return (await session.execute(select(Balance.credits_remaining)
                                  .where(Balance.company_id == company_id))).scalar_one()


@pytest.mark.asyncio
async def test_the_preview_is_numbers_only(client, session):  # noqa: F811
    """מספר לפני החיוב — ושום דבר שמזהה מגרש."""
    await _credits(session, client.user.company_id, 3)
    for block, cap, ready in (("9501", 9000, True), ("9502", 8000, False),
                              ("9503", 7000, True), ("9504", 6000, True)):
        await _parcel(session, block, cap, ready)

    r = await client.post("/api/v1/candidates/herzliya/scan/preview", json=BY_CAP)
    assert r.status_code == 200
    body = r.json()
    assert body == {"found": 4, "offer": 3, "ready": 3, "needs_fetch": 0, "credits_remaining": 3}
    assert "רחוב הסריקה" not in r.text and "9501" not in r.text
    assert await _balance(session, client.user.company_id) == 3     # תצוגה אינה מחייבת


@pytest.mark.asyncio
async def test_a_scan_delivers_ready_parcels_first_in_the_customers_order(client, session):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    unready = await _parcel(session, "9511", 9900, ready=False)       # הגבוה ביותר, אבל לא מוכן
    top = [await _parcel(session, b, c) for b, c in (("9512", 9000), ("9513", 8000), ("9514", 7000))]
    left_out = await _parcel(session, "9515", 6000)

    r = await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)
    assert r.status_code == 200
    body = r.json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(o.id) for o in top]
    assert body["delivered"][0]["geometry"]["type"] == "MultiPolygon"
    assert body["skipped"] == 0 and body["retryable"] is False
    assert body["credits_remaining"] == 0
    # מה שלא נמסר אינו מופיע בתשובה בשום צורה
    assert str(unready.id) not in r.text and str(left_out.id) not in r.text
    assert "9511" not in r.text and "9515" not in r.text


@pytest.mark.asyncio
async def test_a_parcel_that_cannot_be_delivered_is_skipped_and_not_charged(client, session, monkeypatch):  # noqa: F811
    await _credits(session, client.user.company_id, 5)
    ready = [str((await _parcel(session, b, c)).id) for b, c in (("9521", 9000), ("9522", 8000))]
    await _parcel(session, "9523", 7000, ready=False)

    async def no_answer(s, oid):          # השליפה לא ענתה על השער
        return False
    monkeypatch.setattr(api, "fetch_for_delivery", no_answer)

    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert {d["opportunity_id"] for d in body["delivered"]} == set(ready)
    assert body["skipped"] == 1
    assert body["credits_remaining"] == 3                              # שתיים חויבו, לא שלוש


@pytest.mark.asyncio
async def test_a_second_scan_completes_what_the_first_left(client, session):  # noqa: F811
    """נמצאו רק שניים — הזכאות שנשארה משמשת לאזור הבא, והמגרשים שנמסרו
    אינם מוצעים שוב (SEL-02)."""
    await _credits(session, client.user.company_id, 3)
    first = [await _parcel(session, b, c) for b, c in (("9531", 9000), ("9532", 8000))]
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert len(body["delivered"]) == 2 and body["credits_remaining"] == 1

    await _parcel(session, "9533", 5000)
    preview = (await client.post("/api/v1/candidates/herzliya/scan/preview", json=BY_CAP)).json()
    assert preview == {"found": 1, "offer": 1, "ready": 1, "needs_fetch": 0, "credits_remaining": 1}
    again = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert [d["address"] for d in again["delivered"]] == ["רחוב הסריקה 9533"]
    assert {str(o.id) for o in first}.isdisjoint(d["opportunity_id"] for d in again["delivered"])


@pytest.mark.asyncio
async def test_no_credits_is_402_before_anything_is_searched(client, session):  # noqa: F811
    await _parcel(session, "9541", 9000)
    r = await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)
    assert r.status_code == 402
    preview = (await client.post("/api/v1/candidates/herzliya/scan/preview", json=BY_CAP)).json()
    assert preview["offer"] == 0 and preview["credits_remaining"] == 0


@pytest.mark.asyncio
async def test_an_empty_area_charges_nothing(client, session):  # noqa: F811
    """‏ACC-03: סריקה ריקה אינה מפחיתה זכאות."""
    await _credits(session, client.user.company_id, 3)
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert body["delivered"] == [] and body["credits_remaining"] == 3
    # ‏״אין הזדמנויות באזור״ ולא ״נכשל״: המסך מבחין ביניהם לפי `found`.
    assert body["found"] == 0


@pytest.mark.asyncio
async def test_a_complete_dossiers_scan_never_fetches_from_the_archive(client, session, monkeypatch):  # noqa: F811
    """‏`ready_only` (טל, 16.09): רק מגרשים שתיק הבניין שלהם כבר שלם. מגרש שדורש
    שליפה אינו נמסר ואינו נשלף — גם כשהוא הגבוה ביותר בסדר ההעדפות."""
    await _credits(session, client.user.company_id, 3)
    await _parcel(session, "9561", 9900, ready=False)
    ready = [str((await _parcel(session, b, c)).id) for b, c in (("9562", 9000), ("9563", 8000))]

    async def no_fetch(*_a, **_k):
        raise AssertionError("ready_only must not touch the archive")
    monkeypatch.setattr(api, "fetch_for_delivery", no_fetch)

    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json=BY_CAP | {"ready_only": True})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == ready
    assert body["found"] == 2 and body["credits_remaining"] == 1


@pytest.mark.asyncio
async def test_an_archive_refusal_keeps_what_was_delivered_and_says_retry(client, session, monkeypatch):  # noqa: F811
    company = client.user.company_id
    await _credits(session, company, 3)
    ready = str((await _parcel(session, "9551", 9000)).id)
    await _parcel(session, "9552", 8000, ready=False)

    async def refused(s, oid):
        raise ArchiveUnavailable("הארכיון סירב")
    monkeypatch.setattr(api, "fetch_for_delivery", refused)

    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [ready]
    assert body["retryable"] is True and body["message"]
    assert body["credits_remaining"] == 2
    # נשמר, ולא גולגל לאחור יחד עם השליפה שנכשלה
    from app.models.package import Delivery
    kept = (await session.execute(select(Delivery.opportunity_id)
                                  .where(Delivery.company_id == company))).scalars().all()
    assert [str(k) for k in kept] == [ready]


@pytest.mark.asyncio
async def test_a_bad_area_is_refused_not_treated_as_the_whole_city(client, session):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    outside = {"type": "Polygon", "coordinates": [[[34.77, 32.07], [34.78, 32.07],
                                                   [34.78, 32.08], [34.77, 32.08], [34.77, 32.07]]]}
    for path in ("preview", "deliver"):
        r = await client.post(f"/api/v1/candidates/herzliya/scan/{path}", json={"polygon": outside})
        assert r.status_code == 422, (path, json.dumps(r.json(), ensure_ascii=False))
    assert await _balance(session, client.user.company_id) == 3
