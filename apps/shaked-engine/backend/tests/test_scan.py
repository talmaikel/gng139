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

# ‏W6 · הסריקה מדרגת לפי הכלכלה של כל מועמד. במגרשים הסינתטיים כאן אין ראיות
# לתרחיש, ולכן הכלכלה מוזרקת: כברירת מחדל כל מגרש כלכלי, והרווח עולה עם
# התקרה — כך הבדיקות של מוכנות, דילוג וחיוב שומרות על המשמעות שלהן.
# בדיקה שצריכה מקרה אחר קובעת אותו ב-`ECONOMICS[block]`.
ECONOMICS: dict[str, dict] = {}


@pytest.fixture(autouse=True)
def _economics(monkeypatch):
    ECONOMICS.clear()

    async def fake(session, rules, oid):
        opp = await session.get(Opportunity, oid)
        if opp.block in ECONOMICS:
            return ECONOMICS[opp.block]
        cap = ((opp.metadata_json or {}).get("assessment") or {}).get("cap_400_sqm") or 0
        return {"case": "A", "margin": 0.2 + cap / 1e6, "cap_margin": 0.3, "after_levy": True}
    monkeypatch.setattr(api, "parcel_economics", fake)


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
    # המוכנות אינה משנה את הסדר: 9502 בשלושת הראשונים, ויישלף במסירה
    assert body == {"found": 4, "offer": 3, "ready": 2, "needs_fetch": 1, "credits_remaining": 3,
                    "found_economic": 4, "found_rights_request": 0, "needs_rights_confirmation": None}
    assert "רחוב הסריקה" not in r.text and "9501" not in r.text
    assert await _balance(session, client.user.company_id) == 3     # תצוגה אינה מחייבת


async def _passes_on_fetch(s, oid):
    """שליפה שענתה על השער: ההערכה מחדש מסמנת את המגרש כמוכן."""
    opp = await s.get(Opportunity, oid)
    meta = dict(opp.metadata_json)
    meta["assessment"] = {**meta["assessment"], "deliverable": True}
    opp.metadata_json = meta
    await s.flush()
    return True


@pytest.mark.asyncio
async def test_a_scan_delivers_in_order_and_leaves_the_rest_unseen(client, session, monkeypatch):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    monkeypatch.setattr(api, "fetch_for_delivery", _passes_on_fetch)
    top = [await _parcel(session, b, c) for b, c in (("9512", 9000), ("9513", 8000), ("9514", 7000))]
    left_out = await _parcel(session, "9515", 6000, ready=False)

    r = await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)
    assert r.status_code == 200
    body = r.json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(o.id) for o in top]
    assert body["delivered"][0]["geometry"]["type"] == "MultiPolygon"
    assert body["skipped"] == 0 and body["retryable"] is False
    assert body["credits_remaining"] == 0
    # מה שלא נמסר אינו מופיע בתשובה בשום צורה
    assert str(left_out.id) not in r.text and "9515" not in r.text


# ── טל, 16.09 · לפי scan.html rev 35: ביטחון ואז רווח, ושליפה חיה אחד-אחד ──

@pytest.mark.asyncio
async def test_confidence_tier_comes_before_profit_and_readiness(client, session, monkeypatch):  # noqa: F811
    """חלקה בשכבה 0 שעוד לא נשלפה עוקפת חלקה מוכנה ורווחית יותר בשכבה 1."""
    await _credits(session, client.user.company_id, 3)
    fetched = []

    async def fetch(s, oid):
        fetched.append(oid)
        return await _passes_on_fetch(s, oid)
    monkeypatch.setattr(api, "fetch_for_delivery", fetch)
    stable = await _parcel(session, "9701", 9000, ready=False)
    rich = await _parcel(session, "9702", 9000)
    stable_poor = await _parcel(session, "9703", 9000)
    ECONOMICS.update({"9701": _econ("A", 0.18, 0.3) | {"tier": 0},
                      "9702": _econ("A", 0.40, 0.5) | {"tier": 1},
                      "9703": _econ("A", 0.17, 0.3) | {"tier": 0}})
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={"polygon": AREA})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [
        str(stable.id), str(stable_poor.id), str(rich.id)]
    assert fetched == [stable.id]


@pytest.mark.asyncio
async def test_a_fetched_parcel_that_fails_is_skipped_for_the_next(client, session, monkeypatch):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    # ‏rollback על מגרש שדולג מגלגל גם את הזריעה שלא נשמרה בבדיקה — לכן העובר ראשון
    passing = await _parcel(session, "9712", 9900, ready=False)
    failing = await _parcel(session, "9711", 9000, ready=False)
    failing_id, passing_id = failing.id, passing.id

    async def fetch(s, oid):
        if oid == failing_id:
            return False                  # התיק נקרא ולא ענה על השער
        return await _passes_on_fetch(s, oid)
    monkeypatch.setattr(api, "fetch_for_delivery", fetch)
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(passing_id)], body
    assert body["skipped_ids"] == [str(failing_id)] and body["checked"] == 2
    assert body["more"] is False and body["credits_remaining"] == 2


@pytest.mark.asyncio
async def test_past_the_time_budget_no_new_fetch_starts_and_the_scan_continues(client, session, monkeypatch):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    monkeypatch.setattr(api, "SCAN_TIME_BUDGET_S", 0.0)
    fetched = []

    async def fetch(s, oid):
        fetched.append(oid)
        return await _passes_on_fetch(s, oid)
    monkeypatch.setattr(api, "fetch_for_delivery", fetch)
    ready = await _parcel(session, "9721", 9900)
    later = await _parcel(session, "9722", 9000, ready=False)

    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver", json=BY_CAP)).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(ready.id)]  # מוכן — בלי שליפה
    assert body["more"] is True and fetched == [] and body["retryable"] is False

    monkeypatch.setattr(api, "SCAN_TIME_BUDGET_S", 60.0)
    again = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                               json=BY_CAP | {"want": 2})).json()
    assert [d["opportunity_id"] for d in again["delivered"]] == [str(later.id)]
    assert again["more"] is False and again["credits_remaining"] == 1


@pytest.mark.asyncio
async def test_skip_ids_are_not_fetched_again_and_want_limits_the_delivery(client, session, monkeypatch):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    fetched = []

    async def fetch(s, oid):
        fetched.append(oid)
        return await _passes_on_fetch(s, oid)
    monkeypatch.setattr(api, "fetch_for_delivery", fetch)
    fell = await _parcel(session, "9731", 9900, ready=False)
    a = await _parcel(session, "9732", 9000)
    await _parcel(session, "9733", 8000)
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json=BY_CAP | {"want": 1, "skip_ids": [str(fell.id)]})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(a.id)]
    assert fetched == [] and body["credits_remaining"] == 2


def test_confidence_tier_follows_the_binding_limit():
    from app.cities.herzliya.dossier import confidence_tier
    cap = {"floors": {"low": 7}, "cap_400_sqm": 3000.0}
    assert confidence_tier({"floors": {"low": None}}) == 2
    assert confidence_tier(cap | {"policy_area": {"why": "אין פוליגון"}}) == 2
    assert confidence_tier(cap | {"policy_area": {"binding": "cap", "low": {"sqm": 3000.0}}}) == 0
    assert confidence_tier(cap | {"policy_area": {"binding": "cap", "low": {"sqm": 2400.0}}}) == 1
    assert confidence_tier(cap | {"policy_area": {"binding": "envelope", "low": {"sqm": 2000.0}}}) == 1


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
    assert preview == {"found": 1, "offer": 1, "ready": 1, "needs_fetch": 0, "credits_remaining": 1,
                       "found_economic": 1, "found_rights_request": 0, "needs_rights_confirmation": None}
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


# ── W6 · תנאים ליזם, הרווחיות קודם, והגדלת זכויות רק בסימון ──

def _econ(case, margin, cap_margin):
    return {"case": case, "margin": margin, "cap_margin": cap_margin, "after_levy": True}


@pytest.mark.asyncio
async def test_the_most_profitable_parcels_come_first(client, session):  # noqa: F811
    """בועז, 16.09: שלושת התיקים הם הרווחיים ביותר — לא לפי תקרה ולא לפי מזהה."""
    await _credits(session, client.user.company_id, 3)
    parcels = {b: await _parcel(session, b, 9000) for b in ("9601", "9602", "9603", "9604")}
    for b, m in (("9601", 0.18), ("9602", 0.25), ("9603", 0.20), ("9604", 0.17)):
        ECONOMICS[b] = _econ("A", m, 0.3)
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={"polygon": AREA})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [
        str(parcels[b].id) for b in ("9602", "9603", "9601")]


@pytest.mark.asyncio
async def test_a_parcel_that_is_not_economic_even_at_400_is_never_delivered(client, session):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    await _parcel(session, "9611", 9000)
    ECONOMICS["9611"] = _econ("C", -0.2, 0.11)
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={"polygon": AREA, "include_rights_request": True})).json()
    assert body["delivered"] == [] and body["found"] == 0
    assert body["found_economic"] == 0 and body["found_rights_request"] == 0
    assert body["credits_remaining"] == 3 and await _balance(session, client.user.company_id) == 3


@pytest.mark.asyncio
async def test_a_rights_request_parcel_needs_the_checkbox(client, session):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    await _parcel(session, "9621", 9000)
    ECONOMICS["9621"] = _econ("B", -0.1, 0.22)
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={"polygon": AREA})).json()
    assert body["delivered"] == [] and body["found"] == 0
    assert body["found_rights_request"] == 1             # מספר בלבד — ״סמנו כדי לקבל״
    assert body["needs_rights_confirmation"] is None
    assert await _balance(session, client.user.company_id) == 3


@pytest.mark.asyncio
async def test_with_no_economic_parcel_the_customer_confirms_before_any_address(client, session):  # noqa: F811
    """בועז: *״לפני שהוא נחשף אליו (אסור לו לדעת את הכתובת) הוא צריך לאשר שהוא
    מקבל תיק כלכלי רק עם הגדלת זכויות — או לבצע חיפוש נוסף.״*"""
    await _credits(session, client.user.company_id, 3)
    b = await _parcel(session, "9631", 9000)
    ECONOMICS["9631"] = _econ("B", -0.1, 0.22)
    ask = {"polygon": AREA, "include_rights_request": True}

    r = await client.post("/api/v1/candidates/herzliya/scan/preview", json=ask)
    assert r.json()["needs_rights_confirmation"] == {"count": 1} and r.json()["offer"] == 0

    r = await client.post("/api/v1/candidates/herzliya/scan/deliver", json=ask)
    body = r.json()
    assert body["needs_rights_confirmation"] == {"count": 1}
    assert body["delivered"] == [] and body["credits_remaining"] == 3
    assert str(b.id) not in r.text and "רחוב הסריקה" not in r.text and "9631" not in r.text

    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={**ask, "accept_rights_request": True})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(b.id)]
    assert body["credits_remaining"] == 2


@pytest.mark.asyncio
async def test_with_the_checkbox_rights_requests_follow_the_economic_parcels(client, session):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    a = await _parcel(session, "9641", 9000)
    b = await _parcel(session, "9642", 9000)
    ECONOMICS.update({"9641": _econ("A", 0.18, 0.3), "9642": _econ("B", -0.1, 0.4)})
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={"polygon": AREA, "include_rights_request": True})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(a.id), str(b.id)]
    assert body["needs_rights_confirmation"] is None


@pytest.mark.asyncio
async def test_max_units_and_the_customers_minimum_profit_filter(client, session):  # noqa: F811
    await _credits(session, client.user.company_id, 3)
    small = await _parcel(session, "9651", 9000)
    big = await _parcel(session, "9652", 9000)
    big.existing_units = 40
    await session.flush()
    thin = await _parcel(session, "9653", 9000)
    ECONOMICS.update({"9651": _econ("A", 0.24, 0.3), "9652": _econ("A", 0.30, 0.4),
                      "9653": _econ("A", 0.18, 0.19)})
    body = (await client.post("/api/v1/candidates/herzliya/scan/deliver",
                              json={"polygon": AREA, "max_units": 20, "min_profit_ratio": 0.22})).json()
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(small.id)]
    assert str(big.id) not in str(body) and str(thin.id) not in str(body)
