"""שחזור סיסמה, אימות מייל והגבלת קצב.

המיילים אינם נשלחים: ‏`send_password_reset` ו-`send_verification` מוחלפים
בלוכד, והבדיקה משתמשת בטוקן שנלכד — אותו טוקן שהיה מגיע בקישור.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.core.security as security
from app.core.database import get_async_session
from app.core.rate_limit import ALL_LIMITS, email_account_limit, login_account_limit, signup_ip_limit
from app.main import app
from app.models.tenant import User

API = "/api/v1/auth"
PASSWORD = "long-enough-1"


@pytest.fixture
async def mail(session, monkeypatch):
    """לקוח HTTP ותיבת דואר מדומה: {"reset": [(email, token)], "verify": [...]}."""
    box = {"reset": [], "verify": []}

    async def reset(to, token):
        box["reset"].append((to, token))

    async def verify(to, token):
        box["verify"].append((to, token))

    monkeypatch.setattr(security, "send_password_reset", reset)
    monkeypatch.setattr(security, "send_verification", verify)
    for limit in ALL_LIMITS:
        limit.reset()
    app.dependency_overrides[get_async_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.box = box
        yield c
    app.dependency_overrides.clear()
    for limit in ALL_LIMITS:
        limit.reset()


async def _signup(c, email=None):
    email = email or f"{uuid.uuid4().hex[:8]}@example.com"
    r = await c.post(f"{API}/signup", json={"company_name": "בדיקה", "full_name": "בודק",
                                            "email": email, "password": PASSWORD})
    assert r.status_code == 201
    return email


async def _login(c, email, password, **headers):
    return await c.post(f"{API}/jwt/login", data={"username": email, "password": password},
                        headers=headers)


@pytest.mark.asyncio
async def test_a_forgotten_password_can_be_reset_through_the_emailed_token(mail):
    email = await _signup(mail)
    r = await mail.post(f"{API}/forgot-password", json={"email": email})
    assert r.status_code == 202
    [(to, token)] = mail.box["reset"]
    assert to == email

    r = await mail.post(f"{API}/reset-password", json={"token": token, "password": "a-new-password-2"})
    assert r.status_code == 200
    assert (await _login(mail, email, "a-new-password-2")).status_code == 200
    assert (await _login(mail, email, PASSWORD)).status_code == 400

    # הקישור מת אחרי שימוש: הטוקן כולל טביעה של הסיסמה שהוחלפה
    again = await mail.post(f"{API}/reset-password", json={"token": token, "password": "third-password-3"})
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_forgot_password_does_not_reveal_whether_an_email_is_registered(mail):
    r = await mail.post(f"{API}/forgot-password", json={"email": "nobody-here@example.com"})
    assert r.status_code == 202
    assert mail.box["reset"] == []


@pytest.mark.asyncio
async def test_a_reset_still_enforces_the_password_rules(mail):
    email = await _signup(mail)
    await mail.post(f"{API}/forgot-password", json={"email": email})
    [(_, token)] = mail.box["reset"]
    r = await mail.post(f"{API}/reset-password", json={"token": token, "password": "short"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_signup_sends_a_verification_email_and_the_token_verifies(mail, session):
    email = await _signup(mail)
    [(to, token)] = mail.box["verify"]
    assert to == email

    r = await mail.post(f"{API}/verify", json={"token": token})
    assert r.status_code == 200 and r.json()["is_verified"] is True
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await session.refresh(user)
    assert user.is_verified is True


@pytest.mark.asyncio
async def test_password_guessing_on_one_account_is_stopped(mail):
    """לפי חשבון, ולכן גם כשכל ניסיון מגיע ״מכתובת אחרת״."""
    for i in range(login_account_limit.limit):
        r = await _login(mail, "Victim@example.com", "wrong", **{"X-Forwarded-For": f"10.0.0.{i}"})
        assert r.status_code == 400
    r = await _login(mail, "victim@example.com", "wrong", **{"X-Forwarded-For": "10.9.9.9"})
    assert r.status_code == 429
    assert "יותר מדי" in r.json()["detail"]
    # חשבון אחר אינו נחסם בגלל הראשון
    assert (await _login(mail, "someone-else@example.com", "wrong")).status_code == 400


@pytest.mark.asyncio
async def test_without_a_trusted_header_forwarded_for_is_ignored(mail):
    """‏Next מעביר את X-Forwarded-For של הגולש כמו שהוא — אסור לספור לפיו.
    בלי כותרת מהימנה ומאחורי Next אין כתובת, ואין הגבלה לפי כתובת."""
    body = {"company_name": "בוט", "full_name": "בוט", "password": PASSWORD}
    for _ in range(signup_ip_limit.limit + 2):
        r = await mail.post(f"{API}/signup", headers={"X-Forwarded-For": "198.51.100.4"},
                            json={**body, "email": f"{uuid.uuid4().hex[:8]}@example.com"})
        assert r.status_code == 201


@pytest.mark.asyncio
async def test_signup_is_limited_per_address_from_the_trusted_header(mail, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "trusted_ip_header", "cf-connecting-ip")
    body = {"company_name": "בוט", "full_name": "בוט", "password": PASSWORD}

    async def signup_from(ip):
        return await mail.post(f"{API}/signup", headers={"CF-Connecting-IP": ip},
                               json={**body, "email": f"{uuid.uuid4().hex[:8]}@example.com"})

    for _ in range(signup_ip_limit.limit):
        assert (await signup_from("198.51.100.4")).status_code == 201
    assert (await signup_from("198.51.100.4")).status_code == 429
    assert (await signup_from("198.51.100.5")).status_code == 201


@pytest.mark.asyncio
async def test_reset_emails_to_one_address_are_capped(mail):
    """מי שמנסה להציף תיבה של מישהו בבקשות שחזור נעצר אחרי כמה."""
    email = await _signup(mail)
    for _ in range(email_account_limit.limit):
        assert (await mail.post(f"{API}/forgot-password", json={"email": email})).status_code == 202
    assert (await mail.post(f"{API}/forgot-password", json={"email": email.upper()})).status_code == 429
    assert len(mail.box["reset"]) == email_account_limit.limit


@pytest.mark.asyncio
async def test_without_a_resend_key_the_email_is_logged_not_sent(monkeypatch, caplog):
    """פיתוח מקומי ובדיקות אינם שולחים דבר החוצה — הקישור מופיע בלוג."""
    from app.core.config import get_settings
    from app.services import email as email_service

    monkeypatch.setattr(get_settings(), "resend_api_key", None)
    monkeypatch.setattr(get_settings(), "resend_api_key_file", "no-such-file.key")

    async def refuse(*_a, **_k):
        raise AssertionError("אין לפנות ל-Resend בלי מפתח")

    monkeypatch.setattr(email_service.httpx.AsyncClient, "post", refuse)
    with caplog.at_level("WARNING", logger="shaked.email"):
        sent = await email_service.send_password_reset("someone@example.com", "tok123")
    assert sent is False
    assert "reset-password?token=tok123" in caplog.text
