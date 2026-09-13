"""רישום המסירות — ‏SEL-02, ‏ACC-04, ‏ACC-05, ‏ACC-06.

לפני זה היו ל-engine ‏`packages`, ‏`balances` ו-`reservations` — ולא טבלת
מסירות. ``reservations`` הוא נעילה זמנית ואינו זוכר מה נמסר, ולכן הדרישה
המרכזית של ה-PRD לא הייתה ניתנת לאכיפה: *״אותו מגרש אינו נספר שוב בעקבות
פוליגון חופף, שינוי כתובת, שינוי משתמש בחברה או חבילה חדשה״*.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.package import Balance, Delivery
from app.models.tenant import Company, User
from app.services.deliveries import (NoCredits, NotDeliverable, deliver, delivered_ids)

SQUARE = ("MULTIPOLYGON(((34.8440000 32.1640000,34.8444000 32.1640000,"
          "34.8444000 32.1643000,34.8440000 32.1643000,34.8440000 32.1640000)))")


async def _company(session, name="חברת בדיקה", credits=3):
    c = Company(name=name, slug=f"d-{uuid.uuid4().hex[:8]}")
    session.add(c)
    await session.flush()
    session.add(Balance(company_id=c.id, credits_remaining=credits))
    users = []
    for i in range(2):
        u = User(email=f"{uuid.uuid4().hex[:8]}@d.local", hashed_password="x",
                 is_active=True, is_superuser=False, is_verified=True,
                 full_name=f"משתמש {i}", role="member", company_id=c.id)
        session.add(u)
        users.append(u)
    await session.flush()
    return c, users


async def _opportunity(session, block, *, deliverable=True, open_gates=()):
    opp = Opportunity(
        city_code="herzliya", address=f"רחוב המסירה {block}", block=block,
        block_suffix=0, parcel="1", geom=f"SRID=4326;{SQUARE}",
        verification_level=VerificationLevel.RAW.value,
        metadata_json={"assessment": {"status": "needs_verification",
                                      "deliverable": deliverable,
                                      "threshold_open": list(open_gates)}})
    session.add(opp)
    await session.flush()
    return opp


# ── SEL-02 · אותו מגרש אינו נספר פעמיים ──

@pytest.mark.asyncio
async def test_delivering_the_same_parcel_twice_charges_once(session):
    c, (u, _) = await _company(session)
    opp = await _opportunity(session, "9301")

    row, charged = await deliver(session, opp.id, c.id, u.id)
    assert charged is True

    again, charged2 = await deliver(session, opp.id, c.id, u.id)
    assert charged2 is False
    assert again.id == row.id
    assert (await session.get(Balance, (await session.execute(
        select(Balance).where(Balance.company_id == c.id))).scalar_one().id)
    ).credits_remaining == 2


@pytest.mark.asyncio
async def test_a_second_user_in_the_same_company_does_not_pay_again(session):
    """‏ACC-04: *״שני משתמשים באותה חברה סורקים פוליגונים חופפים: אותה
    הזדמנות נמסרת פעם אחת״*. הבעלות היא של החברה — *״תוצאה שנמסרה למשתמש
    בחברה נחשבת תוצאה שנמסרה לחברה״*."""
    c, (first, second) = await _company(session)
    opp = await _opportunity(session, "9302")

    row, charged = await deliver(session, opp.id, c.id, first.id)
    same, charged2 = await deliver(session, opp.id, c.id, second.id)
    assert (charged, charged2) == (True, False)
    assert same.id == row.id
    # ומי קיבל אותה במקור אינו משתנה בדיעבד
    assert same.delivered_to_user_id == first.id


@pytest.mark.asyncio
async def test_a_new_package_does_not_reopen_a_parcel_already_delivered(session):
    """*״...או חבילה חדשה״*. חידוש יתרה אינו מוחק מה שכבר נמסר."""
    c, (u, _) = await _company(session, credits=1)
    opp = await _opportunity(session, "9303")
    await deliver(session, opp.id, c.id, u.id)

    balance = (await session.execute(select(Balance).where(Balance.company_id == c.id))).scalar_one()
    balance.credits_remaining = 3          # חבילה חדשה
    await session.flush()

    _, charged = await deliver(session, opp.id, c.id, u.id)
    assert charged is False
    assert balance.credits_remaining == 3


@pytest.mark.asyncio
async def test_two_different_companies_may_each_receive_the_same_parcel(session):
    """האילוץ הוא על (הזדמנות, חברה). מגרש אחד יכול להימסר לשתי חברות —
    מניעת התנגשות ביניהן היא תפקידו של השריון, לא של רישום המסירה."""
    a, (ua, _) = await _company(session, "חברה א")
    b, (ub, _) = await _company(session, "חברה ב")
    opp = await _opportunity(session, "9304")

    _, first = await deliver(session, opp.id, a.id, ua.id)
    _, second = await deliver(session, opp.id, b.id, ub.id)
    assert first is True and second is True


@pytest.mark.asyncio
async def test_a_delivery_survives_someone_elses_later_reservation(session):
    """‏ACC-06: *״חברה א׳ קיבלה תיק לפני שחברה ב׳ הפעילה שריון: א׳ שומרת
    גישה״*. אין בשורה שדה סטטוס, ואין דרך למחוק אותה."""
    from app.models.package import Reservation, ReservationStatus
    a, (ua, _) = await _company(session, "חברה א")
    b, _ = await _company(session, "חברה ב")
    opp = await _opportunity(session, "9305")
    await deliver(session, opp.id, a.id, ua.id)

    session.add(Reservation(opportunity_id=opp.id, company_id=b.id,
                            status=ReservationStatus.ACTIVE,
                            expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    await session.flush()
    assert opp.id in await delivered_ids(session, a.id)


# ── ACC-05 · מועמד לא מוכן אינו צורך יתרה ──

@pytest.mark.asyncio
async def test_an_unready_candidate_is_refused_and_costs_nothing(session):
    """‏`deliverable` הוא False כל עוד שער סף של §70א לא נשאל — כלומר כל
    עוד לא נמשך תיק הבניין. זה מכוון: הארכיון נשלף לפי דרישת לקוח."""
    c, (u, _) = await _company(session)
    opp = await _opportunity(session, "9306", deliverable=False,
                             open_gates=("permit_date", "strengthened"))
    with pytest.raises(NotDeliverable, match="permit_date"):
        await deliver(session, opp.id, c.id, u.id)
    balance = (await session.execute(select(Balance).where(Balance.company_id == c.id))).scalar_one()
    assert balance.credits_remaining == 3
    assert await delivered_ids(session, c.id) == set()


@pytest.mark.asyncio
async def test_an_unknown_opportunity_is_refused_rather_than_delivered(session):
    c, (u, _) = await _company(session)
    with pytest.raises(NotDeliverable):
        await deliver(session, uuid.uuid4(), c.id, u.id)


# ── היתרה ──

@pytest.mark.asyncio
async def test_delivery_stops_when_the_entitlement_runs_out(session):
    c, (u, _) = await _company(session, credits=1)
    first = await _opportunity(session, "9307")
    second = await _opportunity(session, "9308")
    await deliver(session, first.id, c.id, u.id)
    with pytest.raises(NoCredits):
        await deliver(session, second.id, c.id, u.id)
    # ושורה לא נוצרה בדרך
    assert await delivered_ids(session, c.id) == {first.id}


@pytest.mark.asyncio
async def test_a_repeat_delivery_works_even_with_no_credits_left(session):
    """מה שנמסר כבר שולם עליו. יתרה שאזלה אינה שוללת גישה למה שכבר בבעלות."""
    c, (u, _) = await _company(session, credits=1)
    opp = await _opportunity(session, "9309")
    await deliver(session, opp.id, c.id, u.id)
    _, charged = await deliver(session, opp.id, c.id, u.id)
    assert charged is False


# ── SEL-01 · הנימוק וגרסאות נשמרים ──

@pytest.mark.asyncio
async def test_the_reason_and_the_versions_are_kept_with_the_delivery(session):
    """*״נשמרים גרסת הנתונים, גרסת הכללים והנימוק לכל בחירה״*. בלעדיהם אין
    דרך לענות ללקוח למה דווקא המגרש הזה נבחר לפני חצי שנה."""
    c, (u, _) = await _company(session)
    opp = await _opportunity(session, "9310")
    row, _ = await deliver(session, opp.id, c.id, u.id,
                           why={"preferences": ["cap_400"], "rank": 1},
                           rules_version="policy-2026-02", data_version="layer-a-2026-09")
    assert row.why_selected["rank"] == 1
    assert (row.rules_version, row.data_version) == ("policy-2026-02", "layer-a-2026-09")


# ── האילוץ עצמו ──

@pytest.mark.asyncio
async def test_the_database_refuses_a_duplicate_even_if_the_code_does_not(session):
    """הבדיקה בקוד יכולה להפסיד מרוץ בין שתי סריקות במקביל. ההגנה האמיתית
    היא האילוץ הייחודי, והבדיקה הזו עוקפת את `deliver()` כדי לאמת אותו."""
    from sqlalchemy.exc import IntegrityError
    c, (u, _) = await _company(session)
    opp = await _opportunity(session, "9311")
    await deliver(session, opp.id, c.id, u.id)
    session.add(Delivery(opportunity_id=opp.id, company_id=c.id, credits_charged=1))
    with pytest.raises(IntegrityError):
        await session.flush()
