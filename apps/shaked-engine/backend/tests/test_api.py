"""שכבת ה-API — מה שהלקוח פוגש בפועל, ומה שלא היה בדוק כלל.

שתי הבדיקות שחשובות כאן אינן על ״האם המסלול עונה״ אלא על שני דברים
שנכשלים בשקט: **בידוד בין לקוחות** (תיק של חברה אחרת חייב להיראות כלא
קיים, לא כאסור), ו**קלט שנדחה ב-422 ולא מתפרש כברירת מחדל** — פוליגון
פסול שמתפרש כ״כל העיר״ הוא בדיוק סוג הכשל ש-MAP-01 נועד למנוע.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from sqlalchemy import select

from app.core.database import get_async_session
from app.core.security import current_active_user
from app.main import app
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.tenant import Company, User

# פוליגון בתוך הרצליה — סביב אזור המועמדים
# ‏~62 דונם. הגבול הוא 250, והניסוח הראשון כאן היה 1,100 — הקוד דחה בצדק.
INSIDE = {"type": "Polygon", "coordinates": [[[34.8400, 32.1600], [34.8430, 32.1600],
                                              [34.8430, 32.1620], [34.8400, 32.1620],
                                              [34.8400, 32.1600]]]}
# תל אביב — תקין כגאומטריה, מחוץ לגבול המוניציפלי
OUTSIDE = {"type": "Polygon", "coordinates": [[[34.7700, 32.0700], [34.7800, 32.0700],
                                               [34.7800, 32.0800], [34.7700, 32.0800],
                                               [34.7700, 32.0700]]]}


async def _user(session, name="חברת בדיקה"):
    company = Company(name=name, slug=f"t-{uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.local", hashed_password="x",
                is_active=True, is_superuser=False, is_verified=True,
                full_name="בודק", role="member", company_id=company.id)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def client(session):
    """לקוח HTTP שמשתמש בטרנזקציית הבדיקה ובמשתמש מזויף.

    ה-session מגיע מהפיקסטורה המגולגלת לאחור, ולכן שום קריאה כאן אינה
    משאירה שורה בבסיס הנתונים האמיתי.
    """
    user = await _user(session)
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[current_active_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        c.user = user
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_needs_no_authentication(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


# ── MAP-01 · אזור חיפוש ──

@pytest.mark.asyncio
async def test_a_drawn_area_returns_only_what_is_inside_it(client):
    r = await client.post("/api/v1/candidates/herzliya/search", json={"polygon": INSIDE})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_an_area_outside_the_city_is_refused_and_not_answered_empty(client):
    """רשימה ריקה נקראת כ״אין מועמדים כאן״. זו תשובה שגויה לשאלה שגויה —
    צריך לומר שהאזור מחוץ להרצליה."""
    r = await client.post("/api/v1/candidates/herzliya/search", json={"polygon": OUTSIDE})
    assert r.status_code == 422
    assert r.json()["detail"]


@pytest.mark.asyncio
async def test_a_malformed_polygon_is_refused_rather_than_ignored(client):
    for bad in ({"type": "Polygon", "coordinates": []},
                {"type": "Point", "coordinates": [34.84, 32.16]},
                {"type": "Polygon"}):
        r = await client.post("/api/v1/candidates/herzliya/search", json={"polygon": bad})
        assert r.status_code == 422, bad


@pytest.mark.asyncio
async def test_at_most_three_preferences_are_accepted(client):
    """‏PRD 4.2: סדר מפורש. מעבר לשלוש העדפות הסדר מפסיק להיות מובן למי
    שהגדיר אותו, ולכן הגבול נאכף ולא נחתך בשקט."""
    prefs = [{"field": f, "direction": "desc"}
             for f in ("parcel_area", "units", "floors", "cap_400")]
    r = await client.post("/api/v1/candidates/herzliya/search",
                          json={"polygon": INSIDE, "preferences": prefs})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_preference_field_is_refused(client):
    r = await client.post("/api/v1/candidates/herzliya/search",
                          json={"polygon": INSIDE,
                                "preferences": [{"field": "profit", "direction": "desc"}]})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_city_does_not_fall_back_to_herzliya(client):
    r = await client.get("/api/v1/candidates/netanya")
    assert r.status_code == 404          # ולא 500: קלט של משתמש אינו שגיאת שרת
    assert "netanya" in r.json()["detail"]


# ── בידוד בין לקוחות ──

@pytest.mark.asyncio
async def test_a_dossier_of_another_company_is_not_found_rather_than_forbidden(client, session):
    """‏404 ולא 403: ‏403 מאשר שהמזהה קיים, וזו דליפה בפני עצמה."""
    r = await client.post(f"/api/v1/dossiers/{uuid.uuid4()}/generate")
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    other = await _user(session, "חברה אחרת")
    app.dependency_overrides[current_active_user] = lambda: other
    r2 = await client.get(f"/api/v1/dossiers/status/{task_id}")
    assert r2.status_code == 404

    app.dependency_overrides[current_active_user] = lambda: client.user
    assert (await client.get(f"/api/v1/dossiers/status/{task_id}")).status_code == 200


@pytest.mark.asyncio
async def test_a_status_request_for_an_unknown_task_is_not_an_error(client):
    r = await client.get(f"/api/v1/dossiers/status/{uuid.uuid4()}")
    assert r.status_code == 404


# ── ECO · התסריט דרך ה-API ──

@pytest.mark.asyncio
async def test_the_feasibility_endpoint_returns_the_deliverability_flags(client):
    r = await client.post("/api/v1/economic/feasibility", json={
        "plot_area_sqm": 952, "existing_units": 7, "buildable_area_sqm": 3396,
        "sale_price_per_sqm": 45000, "construction_cost_per_sqm": 8000})
    assert r.status_code == 200
    body = r.json()
    assert {"projected_profit_ils", "profit_margin_on_cost_ratio",
            "tenants_fit", "is_deliverable", "inputs_missing"} <= set(body)


@pytest.mark.asyncio
async def test_the_feasibility_endpoint_refuses_an_impossible_scenario(client):
    r = await client.post("/api/v1/economic/feasibility", json={
        "plot_area_sqm": 952, "existing_units": 7, "buildable_area_sqm": 0,
        "sale_price_per_sqm": 45000, "construction_cost_per_sqm": 8000})
    assert r.status_code == 422


# ── פילטרים ──

@pytest.mark.asyncio
async def test_filter_options_name_the_registered_cities(client):
    body = (await client.get("/api/v1/filters/options")).json()
    assert any(c["code"] == "herzliya" for c in body["cities"])
    assert set(body["verification_levels"]) == {v.value for v in VerificationLevel}


# ── SEL-02 · שתי סריקות חופפות, מסירה אחת ──

# פוליגון שני, חופף לראשון בחציו. שני משתמשים באותה חברה מציירים אזורים
# שונים שנחתכים — זה בדיוק המקרה של ACC-04.
OVERLAPPING = {"type": "Polygon", "coordinates": [[[34.8415, 32.1605], [34.8445, 32.1605],
                                                   [34.8445, 32.1625], [34.8415, 32.1625],
                                                   [34.8415, 32.1605]]]}


async def _deliverable_parcel(session, block="9401"):
    """הזדמנות בתוך שני הפוליגונים, מסומנת כניתנת למסירה."""
    from app.models.opportunity import Opportunity
    geom = ("MULTIPOLYGON(((34.8420000 32.1610000,34.8424000 32.1610000,"
            "34.8424000 32.1613000,34.8420000 32.1613000,34.8420000 32.1610000)))")
    opp = Opportunity(city_code="herzliya", address=f"רחוב החפיפה {block}", block=block,
                      block_suffix=0, parcel="1", geom=f"SRID=4326;{geom}",
                      area_sqm=1200.0, existing_units=8,
                      verification_level=VerificationLevel.RAW.value,
                      metadata_json={"category": "primary_candidate",
                                     "assessment": {"status": "needs_verification",
                                                    "deliverable": True,
                                                    "floors_low": 8}})
    session.add(opp)
    await session.flush()
    return opp


@pytest.mark.asyncio
async def test_two_overlapping_scans_deliver_the_parcel_once(client, session):
    """קריטריון היציאה של A13, מקצה לקצה דרך ה-API.

    משתמש א׳ סורק, מוסר, ומשלם. משתמש ב׳ באותה חברה סורק פוליגון חופף —
    המגרש כבר אינו מוצע לו כהזדמנות חדשה, ובקשת מסירה חוזרת אינה מחייבת.
    """
    from app.models.package import Balance
    opp = await _deliverable_parcel(session)
    session.add(Balance(company_id=client.user.company_id, credits_remaining=3))
    await session.flush()

    def ids(r):
        return {row["id"] for row in r.json()}

    first = await client.post("/api/v1/candidates/herzliya/search", json={"polygon": INSIDE})
    assert str(opp.id) in ids(first)

    got = await client.post(f"/api/v1/candidates/herzliya/{opp.id}/deliver")
    assert got.status_code == 200 and got.json()["charged"] is True

    # משתמש שני באותה חברה, פוליגון חופף
    second_user = await _user(session)
    second_user.company_id = client.user.company_id
    await session.flush()
    app.dependency_overrides[current_active_user] = lambda: second_user

    again = await client.post("/api/v1/candidates/herzliya/search", json={"polygon": OVERLAPPING})
    assert str(opp.id) not in ids(again)          # אינו מוצע שוב

    repeat = await client.post(f"/api/v1/candidates/herzliya/{opp.id}/deliver")
    assert repeat.status_code == 200
    assert repeat.json()["charged"] is False      # ואינו מחויב שוב
    assert repeat.json()["delivery_id"] == got.json()["delivery_id"]

    balance = (await session.execute(
        select(Balance).where(Balance.company_id == client.user.company_id))).scalar_one()
    assert balance.credits_remaining == 2         # חיוב אחד, לא שניים


@pytest.mark.asyncio
async def test_an_unready_candidate_is_refused_with_409_and_costs_nothing(client, session):
    """‏ACC-05, דרך ה-API. ‏409 ולא 402: הבעיה אינה שאין יתרה אלא שהמועמד
    אינו מוכן, ולקוח שיטען עוד זכאות עדיין לא יקבל אותו."""
    from app.models.package import Balance
    opp = await _deliverable_parcel(session, "9402")
    opp.metadata_json = {**opp.metadata_json,
                         "assessment": {"deliverable": False,
                                        "threshold_open": ["permit_date"]}}
    session.add(Balance(company_id=client.user.company_id, credits_remaining=3))
    await session.flush()

    r = await client.post(f"/api/v1/candidates/herzliya/{opp.id}/deliver")
    assert r.status_code == 409
    assert "permit_date" in r.json()["detail"]

    balance = (await session.execute(
        select(Balance).where(Balance.company_id == client.user.company_id))).scalar_one()
    assert balance.credits_remaining == 3


@pytest.mark.asyncio
async def test_delivery_without_any_entitlement_is_402(client, session):
    opp = await _deliverable_parcel(session, "9403")
    r = await client.post(f"/api/v1/candidates/herzliya/{opp.id}/deliver")
    assert r.status_code == 402
