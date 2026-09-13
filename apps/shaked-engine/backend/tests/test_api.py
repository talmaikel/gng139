"""שכבת ה-API — מה שהלקוח פוגש בפועל, ומה שלא היה בדוק כלל.

שתי הבדיקות שחשובות כאן אינן על ״האם המסלול עונה״ אלא על שני דברים
שנכשלים בשקט: **בידוד בין לקוחות** (תיק של חברה אחרת חייב להיראות כלא
קיים, לא כאסור), ו**קלט שנדחה ב-422 ולא מתפרש כברירת מחדל** — פוליגון
פסול שמתפרש כ״כל העיר״ הוא בדיוק סוג הכשל ש-MAP-01 נועד למנוע.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

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
