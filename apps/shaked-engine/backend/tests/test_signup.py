"""הרשמת לקוח — ומה שהרשמה אסור שתאפשר.

הבדיקות החשובות כאן אינן ״ההרשמה עובדת״ אלא שתי הפרצות שהיא סגרה:
הצטרפות לחברה קיימת דרך `company_id` שנשלח מהדפדפן, והעלאה עצמית
ל-owner דרך `role`.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import get_async_session
from app.core.security import get_jwt_strategy
from app.main import app
from app.models.tenant import Company, User

SIGNUP = "/api/v1/auth/signup"


@pytest.fixture
async def anon(session):
    """לקוח HTTP בלי משתמש מחובר — מי שנרשם עוד אין לו חשבון."""
    app.dependency_overrides[get_async_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _body(**over):
    body = {"company_name": "יזמות בדיקה", "full_name": "נועה לוי",
            "email": f"{uuid.uuid4().hex[:8]}@example.com", "password": "long-enough-1"}
    body.update(over)
    return body


async def _by_email(session, email):
    return (await session.execute(
        select(User).where(User.email == email))).scalar_one_or_none()


@pytest.mark.asyncio
async def test_signup_opens_a_new_company_with_the_user_as_owner(anon, session):
    body = _body()
    r = await anon.post(SIGNUP, json=body)
    assert r.status_code == 201
    assert r.json()["access_token"]

    user = await _by_email(session, body["email"])
    assert user.role == "owner"
    company = await session.get(Company, user.company_id)
    assert company.name == "יזמות בדיקה"


@pytest.mark.asyncio
async def test_signup_ignores_a_company_id_and_role_sent_by_the_browser(anon, session):
    """הפרצה שנסגרה: להירשם לתוך חברה קיימת."""
    victim = Company(name="חברה קיימת", slug=f"t-{uuid.uuid4().hex[:8]}")
    session.add(victim)
    await session.flush()

    body = _body(company_id=str(victim.id), role="admin")
    r = await anon.post(SIGNUP, json=body)
    assert r.status_code == 201

    user = await _by_email(session, body["email"])
    assert user.company_id != victim.id
    assert user.role == "owner"


@pytest.mark.asyncio
async def test_the_old_open_register_route_is_gone(anon):
    r = await anon.post("/api/v1/auth/register", json={
        "email": "x@example.com", "password": "long-enough-1",
        "full_name": "x", "company_id": str(uuid.uuid4()), "role": "owner"})
    assert r.status_code in (404, 405)


@pytest.mark.asyncio
async def test_a_taken_email_is_refused_and_leaves_no_orphan_company(anon, session):
    body = _body()
    assert (await anon.post(SIGNUP, json=body)).status_code == 201
    companies_before = len((await session.execute(select(Company))).scalars().all())

    r = await anon.post(SIGNUP, json=_body(email=body["email"], company_name="כפילות"))
    assert r.status_code == 409
    assert "קיים" in r.json()["detail"]
    companies_after = len((await session.execute(select(Company))).scalars().all())
    assert companies_after == companies_before


@pytest.mark.asyncio
async def test_a_short_password_is_refused_in_hebrew(anon):
    r = await anon.post(SIGNUP, json=_body(password="short"))
    assert r.status_code == 422
    assert "8" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_user_cannot_promote_themselves(session):
    """‏`PATCH /users/me` עם `role` — השדה פשוט אינו בסכמה."""
    company = Company(name="צוות", slug=f"t-{uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    user = User(email=f"{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
                is_active=True, is_superuser=False, is_verified=True,
                full_name="חבר צוות", role="member", company_id=company.id)
    session.add(user)
    await session.flush()

    # טוקן אמיתי ולא override: נתיב `users/me` נשען על תלות פנימית של
    # FastAPI-Users, ו-override על `current_active_user` היה נותן 401 —
    # ובדיקה ירוקה מהסיבה הלא נכונה.
    token = await get_jwt_strategy().write_token(user)
    app.dependency_overrides[get_async_session] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch("/api/v1/auth/users/me", json={"role": "owner", "full_name": "שונה"},
                              headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    await session.refresh(user)
    assert user.full_name == "שונה"
    assert user.role == "member"
