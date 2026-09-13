"""ריצת קבלה · **נתיבי הכישלון**.

המסלול המאושר עובד ונבדק בדפדפן. מה שלא נבדק אף פעם הוא מה קורה כשמשהו
נכשל — וזה מה שקורה בהדגמה.

הסיכון המרכזי: **הארכיון מסרב**. הוא כבר עשה את זה פעם, ב-12.09, והוא
יעשה את זה שוב. השאלה היחידה היא מה הלקוח רואה.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.cities.herzliya.archive_facts import fetch_for_delivery
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.package import Balance, Delivery
from app.models.tenant import Company, User
from app.services.deliveries import NoCredits, NotDeliverable, deliver

SQUARE = ("MULTIPOLYGON(((34.8480000 32.1680000,34.8484000 32.1680000,"
          "34.8484000 32.1683000,34.8480000 32.1683000,34.8480000 32.1680000)))")


async def _company(session, credits=3):
    c = Company(name="חברת קבלה", slug=f"acc-{uuid.uuid4().hex[:8]}")
    session.add(c)
    await session.flush()
    session.add(Balance(company_id=c.id, credits_remaining=credits))
    u = User(email=f"{uuid.uuid4().hex[:8]}@acc.local", hashed_password="x", is_active=True,
             is_superuser=False, is_verified=True, full_name="בודק", role="member",
             company_id=c.id)
    session.add(u)
    await session.flush()
    return c, u


async def _unasked(session, block="9701"):
    """מועמד שנשאר במסלול ותנאי הסף שלו מעולם לא נשאל — הרוב המוחלט."""
    opp = Opportunity(
        city_code="herzliya", address=f"רחוב הקבלה {block}", block=block, block_suffix=0,
        parcel="1", geom=f"SRID=4326;{SQUARE}", area_sqm=1800.0, existing_units=28,
        verification_level=VerificationLevel.RAW.value,
        metadata_json={"assessment": {"status": "needs_verification", "screenable": True,
                                      "deliverable": False, "floors_low": 8,
                                      "threshold_open": ["permit_date", "strengthened",
                                                         "occupied", "residential_share"]}})
    session.add(opp)
    await session.flush()
    return opp


async def _credits(session, company_id) -> int:
    return (await session.execute(
        select(Balance.credits_remaining).where(Balance.company_id == company_id))).scalar_one()


# ── הארכיון מסרב ──

@pytest.mark.asyncio
async def test_an_archive_refusal_is_not_reported_as_a_question_we_never_asked(session):
    """שאלנו, ונדחינו. ההודעה ״שערי סף שטרם נענו״ אומרת ללקוח שלא טרחנו —
    והוא ילך לחפש את הבעיה אצלנו במקום לנסות שוב בעוד חמש דקות."""
    c, u = await _company(session)
    opp = await _unasked(session)

    with patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.find_tik_ids",
               new=AsyncMock(side_effect=RuntimeError("נדרש אימות משתמש"))):
        with pytest.raises(Exception) as e:
            await deliver(session, opp.id, c.id, u.id, on_unready=fetch_for_delivery)

    message = str(e.value)
    assert "הארכיון" in message, f"ההודעה אינה מזכירה את הארכיון: {message}"
    assert "שטרם נענו" not in message, f"מוצג כאילו לא שאלנו: {message}"


@pytest.mark.asyncio
async def test_an_archive_refusal_does_not_consume_a_credit(session):
    c, u = await _company(session)
    opp = await _unasked(session, "9702")
    before = await _credits(session, c.id)

    with patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.find_tik_ids",
               new=AsyncMock(side_effect=RuntimeError("429"))):
        with pytest.raises(Exception):
            await deliver(session, opp.id, c.id, u.id, on_unready=fetch_for_delivery)

    assert await _credits(session, c.id) == before
    assert (await session.execute(
        select(Delivery).where(Delivery.opportunity_id == opp.id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_parcel_with_no_building_file_says_so_plainly(session):
    """אין תיק — זה ממצא על החלקה, לא תקלה בארכיון, והלקוח לא צריך לנסות
    שוב. שתי מסקנות שונות לגמרי."""
    c, u = await _company(session)
    opp = await _unasked(session, "9703")

    with patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.find_tik_ids",
               new=AsyncMock(return_value=[])):
        with pytest.raises(Exception) as e:
            await deliver(session, opp.id, c.id, u.id, on_unready=fetch_for_delivery)

    assert "תיק" in str(e.value)
    assert "נסה" not in str(e.value) and "שוב" not in str(e.value)


@pytest.mark.asyncio
async def test_an_empty_file_is_a_finding_and_not_a_transport_failure(session):
    """התיק נמשך בהצלחה ואין בו שורות. הן נספרו יחד עם תקלות תקשורת, ולכן
    הלקוח קיבל ״הארכיון לא השיב, נסה שוב״ — והיה מנסה לנצח."""
    from app.cities.herzliya.archive_facts import ArchiveUnavailable, NoBuildingFile
    c, u = await _company(session)
    opp = await _unasked(session, "9704")

    with patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.find_tik_ids",
               new=AsyncMock(return_value=["475"])), \
         patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.file",
               new=AsyncMock(return_value={"html": "<html>אין שורות</html>", "source": {}})):
        with pytest.raises(NoBuildingFile) as e:
            await deliver(session, opp.id, c.id, u.id, on_unready=fetch_for_delivery)

    assert "אין בו" in str(e.value)
    assert not isinstance(e.value, ArchiveUnavailable)


@pytest.mark.asyncio
async def test_a_file_that_answers_leaves_the_remaining_gates_named(session):
    """התיק נקרא והשיב על מה שיש בו. מה שנשאר פתוח הוא תשובה על המועמד."""
    c, u = await _company(session)
    opp = await _unasked(session, "9705")
    page = ("<tr><td>1</td><td>19780028</td><td>12/03/1978</td><td>פתיחת בקשה להיתר</td>"
            "<td>פלוני</td><td>1234</td><td>23/07/1978</td></tr>")

    with patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.find_tik_ids",
               new=AsyncMock(return_value=["475"])), \
         patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.file",
               new=AsyncMock(return_value={"html": page, "source": {}})):
        # אחרי השליפה ההערכה נקראת מחדש. השערים שנותרו פתוחים תלויים
        # בראיות שקיימות, ולכן די בכך שהמסירה אינה מתפרשת כתקלת ארכיון.
        try:
            await deliver(session, opp.id, c.id, u.id, on_unready=fetch_for_delivery)
        except NotDeliverable as exc:
            # מה שנשאר פתוח הוא תשובה על המועמד, לא על הארכיון — והוא
            # אינו מזכיר את השערים שהתיק **כן** ענה עליהם.
            assert "הארכיון" not in str(exc)
            assert "permit_date" not in str(exc)


# ── דרך ה-API: שלושה קודים, שלוש פעולות ──

@pytest.mark.asyncio
async def test_the_three_failures_get_three_different_status_codes(session):
    """‏503 אומר ״נסה שוב״; ‏409 אומר ״לא המועמד הזה״; ‏402 אומר ״קנה״.
    להחזיר את כולן כ-409 פירושו לקוח שמוותר על מועמד תקין לחלוטין כי
    הארכיון היה עסוק לרגע."""
    import uuid as _uuid

    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_async_session
    from app.core.security import current_active_user
    from app.main import app

    c, u = await _company(session)
    opp = await _unasked(session, "9710")
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[current_active_user] = lambda: u

    async def attempt(**mocks):
        with patch("app.cities.herzliya.archive_client.HerzliyaArchiveClient.find_tik_ids",
                   new=AsyncMock(**mocks)):
            async with AsyncClient(transport=ASGITransport(app=app),
                                   base_url="http://test") as http:
                return await http.post(
                    f"/api/v1/candidates/herzliya/{opp.id}/deliver")

    try:
        refused = await attempt(side_effect=RuntimeError("נדרש אימות משתמש"))
        assert refused.status_code == 503, refused.text
        assert "לנסות שוב" in refused.json()["detail"]

        no_file = await attempt(return_value=[])
        assert no_file.status_code == 409
        assert "לנסות שוב" not in no_file.json()["detail"]

        # וגם אחרי שתי דחיות — לא נוכתה זכאות ולא נוצרה מסירה
        assert await _credits(session, c.id) == 3
        assert (await session.execute(
            select(Delivery).where(Delivery.company_id == c.id))).scalars().all() == []
    finally:
        app.dependency_overrides.clear()
