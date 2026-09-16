"""זכאות ידנית בפיילוט — אדמין מוסיף אחרי תשלום, ולקוח לא יכול.

הבדיקה החשובה היא הראשונה: לקוח, גם owner של החברה שלו, אינו מגיע לנתיב.
טוקן אמיתי ולא override — ‏`current_superuser` הוא תלות נפרדת, ו-override
על `current_active_user` לא היה בודק אותה כלל.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import get_async_session
from app.core.security import get_jwt_strategy
from app.main import app
from app.models.package import Balance, CreditGrant, Package
from app.models.tenant import Company, User


async def _member(session, *, superuser=False, role="member", company=None):
    if company is None:
        company = Company(name=f"חברה {uuid.uuid4().hex[:4]}", slug=f"t-{uuid.uuid4().hex[:8]}")
        session.add(company)
        await session.flush()
    user = User(email=f"{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
                is_active=True, is_superuser=superuser, is_verified=True,
                full_name="בודק", role=role, company_id=company.id)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def http(session):
    app.dependency_overrides[get_async_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async def as_user(user):
            c.headers["Authorization"] = f"Bearer {await get_jwt_strategy().write_token(user)}"
        c.as_user = as_user
        yield c
    app.dependency_overrides.clear()


async def _credits(session, company_id):
    row = (await session.execute(
        select(Balance).where(Balance.company_id == company_id))).scalar_one_or_none()
    return row.credits_remaining if row else 0


@pytest.mark.asyncio
async def test_a_customer_owner_cannot_grant_credits_to_its_own_company(http, session):
    owner = await _member(session, role="owner")
    await http.as_user(owner)

    r = await http.post(f"/api/v1/admin/companies/{owner.company_id}/credits",
                        json={"credits": 3, "note": "ניסיון"})
    assert r.status_code == 403
    assert (await http.get("/api/v1/admin/companies")).status_code == 403
    assert await _credits(session, owner.company_id) == 0


@pytest.mark.asyncio
async def test_an_admin_grant_adds_to_the_company_and_is_recorded(http, session):
    """*״הזכאות לשלוש הזדמנויות שייכת לחברה ומשותפת לצוותה״*."""
    admin = await _member(session, superuser=True)
    customer = await _member(session, role="owner")
    teammate = await _member(session, company=await session.get(Company, customer.company_id))
    pkg = Package(name="שלוש הזדמנויות", credits=3, price_ils=30_000)
    session.add(pkg)
    await session.flush()

    await http.as_user(admin)
    r = await http.post(f"/api/v1/admin/companies/{customer.company_id}/credits",
                        json={"package_id": str(pkg.id), "note": "חשבונית 1001"})
    assert r.status_code == 200 and r.json()["credits_remaining"] == 3

    grant = (await session.execute(
        select(CreditGrant).where(CreditGrant.company_id == customer.company_id))).scalar_one()
    assert (grant.credits, grant.note, grant.granted_by_user_id) == (3, "חשבונית 1001", admin.id)

    history = (await http.get(f"/api/v1/admin/companies/{customer.company_id}/credits")).json()
    assert history[0]["granted_by"] == admin.email

    # חבר צוות באותה חברה רואה את אותה יתרה
    await http.as_user(teammate)
    assert (await http.get("/api/v1/account/balance")).json()["credits_remaining"] == 3


@pytest.mark.asyncio
async def test_the_admin_finds_a_company_by_a_member_email(http, session):
    admin = await _member(session, superuser=True)
    customer = await _member(session, role="owner")
    await http.as_user(admin)

    found = (await http.get("/api/v1/admin/companies", params={"q": customer.email.upper()})).json()
    assert [c["id"] for c in found] == [str(customer.company_id)]
    assert found[0]["emails"] == [customer.email]


@pytest.mark.asyncio
async def test_a_grant_without_a_payment_reference_is_refused(http, session):
    admin = await _member(session, superuser=True)
    customer = await _member(session)
    await http.as_user(admin)

    r = await http.post(f"/api/v1/admin/companies/{customer.company_id}/credits",
                        json={"credits": 3, "note": ""})
    assert r.status_code == 422
    r = await http.post(f"/api/v1/admin/companies/{customer.company_id}/credits",
                        json={"note": "חשבונית 7"})
    assert r.status_code == 422
    assert await _credits(session, customer.company_id) == 0


@pytest.mark.asyncio
async def test_a_user_cannot_make_themselves_admin(http, session):
    user = await _member(session)
    await http.as_user(user)
    r = await http.patch("/api/v1/auth/users/me", json={"is_superuser": True})
    assert r.status_code == 200
    await session.refresh(user)
    assert user.is_superuser is False
