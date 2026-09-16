"""‏W5 · בניין שכבר חודש, או בפרויקט חתום — לא נמסר ולא מחויב.

בועז, 16.09: חשד → הצוות מכריע, ועד אז אין מסירה ואין חיוב. אומת → לא נכנס
לסריקה בכלל. הבדיקות כאן על שלושה דברים שנכשלים בשקט: **חיוב** על חלקה
חשודה, חלקה מאומתת שחוזרת ל**תור**, ו״לא נמצא חידוש״ שנכתב **בלי שנבדק**.
"""
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.cities.herzliya import renewal, renewal_signals as RS, rights
from app.cities.herzliya.assessments import refresh_one
from app.cities.herzliya.rules import HerzliyaCityRules, _status
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.package import Balance, Delivery
from app.models.tenant import Company, User
from app.services.deliveries import NotDeliverable, deliver

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# אזור בתוך הגבול העירוני, כמו ב-test_scan
AREA = {"type": "Polygon", "coordinates": [[[34.8100, 32.1600], [34.8120, 32.1600],
                                            [34.8120, 32.1615], [34.8100, 32.1615],
                                            [34.8100, 32.1600]]]}
GEOM = ("MULTIPOLYGON(((34.8105000 32.1605000,34.8109000 32.1605000,"
        "34.8109000 32.1608000,34.8105000 32.1608000,34.8105000 32.1605000)))")

ANSWERED = dict(residential_zoning=True, permit_date="1972-01-01", strengthened=False,
                occupied=False, floors=4, units=28, scope_buildings=1, parcel_area=1100.0,
                street_width=12.0, renewal_policy_category="התחדשות מגרשית מוטת מגורים",
                in_tama70=True, registration_area='שז"ר')
NONE = {"status": "none", "reasons": [], "manual": False}
SUSPECTED = {"status": "suspected", "reasons": ["היתר שניתן אחרי 18.5.2005", "7 קומות בשכבת המבנים"],
             "manual": False}
VERIFIED = {"status": "verified_renewed", "reasons": ["רשימה ידנית: בדיקה"], "manual": True}


async def _parcel(session, block, *, parcel="1", certainty=Certainty.DERIVED, **fields):
    opp = Opportunity(city_code="herzliya", address=f"רחוב החידוש {block}", block=block,
                      block_suffix=0, parcel=parcel, geom=f"SRID=4326;{GEOM}", area_sqm=1100.0,
                      existing_units=28, verification_level=VerificationLevel.RAW.value,
                      metadata_json={"category": "primary_candidate"})
    session.add(opp)
    await session.flush()
    at = datetime.now(timezone.utc) - timedelta(days=1)
    for field, value in fields.items():
        session.add(FieldEvidence(
            opportunity_id=opp.id, field=field, value=value, certainty=certainty.value,
            source_url="https://handasi.complot.co.il/x" if field in renewal.ARCHIVE_INPUTS
            else "https://example.test/x",
            retrieved_at=at, location=f"גוש {block} חלקה {parcel}"))
    await session.flush()
    return opp


async def _company(session, credits=3):
    c = Company(name="חברת חידוש", slug=f"r-{uuid.uuid4().hex[:8]}")
    session.add(c)
    await session.flush()
    session.add(Balance(company_id=c.id, credits_remaining=credits))
    u = User(email=f"{uuid.uuid4().hex[:8]}@r.local", hashed_password="x", is_active=True,
             is_superuser=False, is_verified=True, full_name="בודק", role="member",
             company_id=c.id)
    session.add(u)
    await session.flush()
    return c, u


async def _credits(session, company_id):
    return (await session.execute(select(Balance.credits_remaining)
                                  .where(Balance.company_id == company_id))).scalar_one()


async def _renewal_rows(session, opp_id):
    return (await session.execute(select(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp_id,
        FieldEvidence.field == renewal.FIELD))).scalars().all()


# ── הסימנים ──

@pytest.mark.parametrize("inputs, status", [
    # אלוף יגאל אלון 6: היתר 2017, 7 קומות, 3,392 ברוטו על 1,102
    (dict(post_2005_permit=True, floors=7, built_sqm=3392, lot_sqm=1102), "suspected"),
    (dict(post_2005_permit=True, floors=4, built_sqm=2800, lot_sqm=1100), "suspected"),   # 2.5
    (dict(post_2005_permit=True, floors=4, built_sqm=1000, lot_sqm=1100,
          representative_event=True), "suspected"),
    (dict(post_2005_permit=True, floors=5, built_sqm=2700, lot_sqm=1100), "none"),        # 2.45
    (dict(post_2005_permit=False, floors=9, built_sqm=9000, lot_sqm=1000,
          representative_event=True), "none"),     # היתר אחרי 2005 הוא תנאי
    (dict(post_2005_permit=False, floors=3, built_sqm=900, lot_sqm=1000,
          tama38_event=True), "suspected"),        # תמ״א 38 בארוע עומד לבדו
    (dict(post_2005_permit=None, floors=9, built_sqm=9000, lot_sqm=1000), "unknown"),
    (dict(post_2005_permit=True, floors=None, built_sqm=None, lot_sqm=1000), "unknown"),
])
def test_the_suspicion_truth_table(inputs, status):
    assert RS.signals(**inputs)["status"] == status


def test_a_suspicion_says_why():
    out = RS.signals(post_2005_permit=True, floors=7, built_sqm=3392, lot_sqm=1102,
                     representative_event=True)
    assert out["reasons"] == ["היתר שניתן אחרי 18.5.2005", "7 קומות בשכבת המבנים",
                              "יחס בנוי/מגרש 3.1", "ארוע בבקשה מזכיר מייצג"]


def test_the_manual_list_wins_over_signals():
    entry = {"status": "verified_renewed", "source": "Street View", "note": "9 קומות",
             "checked_by": "חן", "checked_at": "2026-09-17"}
    out = RS.decide(entry, {"status": "none", "reasons": []})
    assert out["status"] == "verified_renewed" and out["manual"] is True
    assert "רשימה ידנית: Street View" in out["reasons"]
    assert RS.decide(None, {"status": "none", "reasons": []})["status"] == "none"


def test_the_manual_list_holds_the_parcels_from_101_and_alon_yigal():
    rows = RS.load_manual()
    assert {"6527/192", "6527/402", "6527/403", "6528/28", "6529/264", "6530/101",
            "6532/371", "6533/255", "6531/156", "6531/152"} <= set(rows)
    for key, e in rows.items():
        assert e["status"] in RS.MANUAL_STATUSES and e["source"], key
    # עוד לא נבדקו בשטח — חן מעלה ל-verified_renewed אחרי Street View
    assert rows["6531/156"]["status"] == "suspected" and rows["6531/156"]["checked_by"] is None


@pytest.mark.parametrize("broken", [
    {"status": "renewed"},              # סטטוס שאינו ברשימה
    {"source": ""},                     # בלי מקור
    {"checked_at": "16.09.2026"},       # תאריך שאינו ISO
])
def test_a_broken_manual_entry_fails_loudly(tmp_path, broken):
    good = {"block": "1", "parcel": "2", "address": "x", "status": "suspected", "source": "s",
            "evidence_url": None, "checked_by": None, "checked_at": None, "note": None}
    p = tmp_path / "list.json"
    p.write_text(json.dumps([{**good, **broken}]), encoding="utf-8")
    with pytest.raises(ValueError):
        RS.load_manual(p)
    p.write_text(json.dumps([good, good]), encoding="utf-8")
    with pytest.raises(ValueError, match="פעמיים"):
        RS.load_manual(p)


# ── השער ──

@pytest.mark.parametrize("value, status, words", [
    (VERIFIED, "failed", "אומת"),
    (SUSPECTED, "needs_review", "7 קומות"),
    (NONE, "passed", "לא נבדק בשטח"),
    ({"status": "none", "reasons": ["בדיקת צוות: הערה פנימית"], "manual": True}, "passed", "נבדק ידנית"),
    (None, "unknown", "לא נבדק"),
])
def test_the_gate_statuses(value, status, words):
    check = rights.renewal_check(value)
    assert (check.id, check.status) == ("not_renewed", status)
    assert words in check.detail
    assert "הערה פנימית" not in check.detail      # הערת צוות אינה בתיק של הלקוח
    assert "not_renewed" in rights.THRESHOLD_IDS


def test_a_suspicion_is_not_a_pass_and_not_a_rejection():
    C = rights.Check
    assert _status([C("a", "a", "passed", "u"), C("not_renewed", "x", "needs_review", "u")]) \
        == "needs_verification"


# ── ההערכה והתור ──

@pytest.mark.asyncio
async def test_a_suspected_parcel_stays_on_the_team_screen_and_is_not_deliverable(session):
    opp = await _parcel(session, "9901", post_2005_permit=True, renewal_status=SUSPECTED, **ANSWERED)
    a = await refresh_one(session, HerzliyaCityRules(), opp.id)
    assert a["screenable"] is True and a["deliverable"] is False and a["under_review"] is True
    assert a["renewal_status"] == "suspected" and "7 קומות בשכבת המבנים" in a["renewal_reasons"]

    rows = await HerzliyaCityRules().screen_candidates(session, {"polygon": AREA})
    row = next(r for r in rows if r["id"] == str(opp.id))
    assert row["renewal_status"] == "suspected" and row["renewal_reasons"]


@pytest.mark.asyncio
async def test_a_verified_renewed_parcel_is_ineligible_and_off_the_list(session):
    opp = await _parcel(session, "9902", post_2005_permit=True, renewal_status=VERIFIED, **ANSWERED)
    a = await refresh_one(session, HerzliyaCityRules(), opp.id)
    assert a["status"] == "ineligible" and a["deliverable"] is False
    rows = await HerzliyaCityRules().screen_candidates(session, {"polygon": AREA})
    assert str(opp.id) not in {r["id"] for r in rows}


@pytest.mark.asyncio
async def test_a_parcel_whose_renewal_was_never_checked_is_not_deliverable(session):
    opp = await _parcel(session, "9903", post_2005_permit=False, **ANSWERED)
    a = await refresh_one(session, HerzliyaCityRules(), opp.id)
    assert "not_renewed" in a["threshold_open"] and a["deliverable"] is False


@pytest.mark.asyncio
async def test_delivery_refuses_a_suspected_parcel_without_fetching_or_charging(session):
    c, u = await _company(session)
    opp = await _parcel(session, "9904", post_2005_permit=True, renewal_status=SUSPECTED, **ANSWERED)
    await refresh_one(session, HerzliyaCityRules(), opp.id)
    calls = []

    async def fetch(s, oid):
        calls.append(oid)
        return True

    with pytest.raises(NotDeliverable, match="ממתין לבדיקת הצוות"):
        await deliver(session, opp.id, c.id, u.id, on_unready=fetch)
    assert calls == []                                  # אין פנייה לארכיון בשביל זה
    assert await _credits(session, c.id) == 3


@pytest.mark.asyncio
async def test_a_scan_never_charges_for_suspected_and_never_offers_verified(session, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.api.v1 import candidates as api
    from app.core.database import get_async_session
    from app.core.security import current_active_user
    from app.main import app

    c, u = await _company(session)
    clean = await _parcel(session, "9911", post_2005_permit=False, renewal_status=NONE, **ANSWERED)
    held = await _parcel(session, "9912", post_2005_permit=True, renewal_status=SUSPECTED, **ANSWERED)
    gone = await _parcel(session, "9913", post_2005_permit=True, renewal_status=VERIFIED, **ANSWERED)
    for o in (clean, held, gone):
        await refresh_one(session, HerzliyaCityRules(), o.id)

    async def never(*_a, **_k):
        raise AssertionError("a held parcel must not reach the archive")
    monkeypatch.setattr(api, "fetch_for_delivery", never)

    # ‏W6 · הסריקה מדרגת לפי כלכלה; כאן הבדיקה היא על החזקה, ולכן כל מגרש כלכלי.
    async def economic(*_a, **_k):
        return {"case": "A", "margin": 0.2, "cap_margin": 0.3, "after_levy": True}
    monkeypatch.setattr(api, "parcel_economics", economic)

    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[current_active_user] = lambda: u
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            preview = (await http.post("/api/v1/candidates/herzliya/scan/preview",
                                       json={"polygon": AREA})).json()
            body = (await http.post("/api/v1/candidates/herzliya/scan/deliver",
                                    json={"polygon": AREA})).json()
    finally:
        app.dependency_overrides.clear()

    assert preview["found"] == 1 and preview["offer"] == 1
    assert [d["opportunity_id"] for d in body["delivered"]] == [str(clean.id)]
    assert body["found"] == 1 and body["credits_remaining"] == 2
    kept = (await session.execute(select(Delivery.opportunity_id)
                                  .where(Delivery.company_id == c.id))).scalars().all()
    assert set(kept) == {clean.id}


# ── הכתיבה ──

@pytest.mark.asyncio
async def test_apply_writes_the_manual_list_as_manually_verified(session, monkeypatch):
    opp = await _parcel(session, "9921", post_2005_permit=False, **ANSWERED)
    entry = {"block": "9921", "parcel": "1", "address": "x", "status": "suspected",
             "source": "issue #101 research", "evidence_url": "https://github.com/x/issues/101",
             "checked_by": None, "checked_at": "2026-09-15", "note": "נבנה מחדש"}
    monkeypatch.setattr(RS, "_manual", lambda: {"9921/1": entry})

    out = await renewal.apply(session, opp)
    assert out["status"] == "suspected"                 # הסימנים אמרו ״לא נמצא״
    (row,) = await _renewal_rows(session, opp.id)
    assert row.certainty == Certainty.MANUALLY_VERIFIED.value
    assert row.source_url == entry["evidence_url"] and row.source_updated_at == "2026-09-15"
    a = await refresh_one(session, HerzliyaCityRules(), opp.id)
    assert a["under_review"] is True and a["deliverable"] is False


@pytest.mark.asyncio
async def test_apply_writes_signals_as_derived_from_the_building_file(session):
    opp = await _parcel(session, "9922", post_2005_permit=True, **{**ANSWERED, "floors": 7})
    assert (await renewal.apply(session, opp))["status"] == "suspected"
    (row,) = await _renewal_rows(session, opp.id)
    assert row.certainty == Certainty.DERIVED.value and "complot" in row.source_url
    assert row.value["reasons"][:2] == ["היתר שניתן אחרי 18.5.2005", "7 קומות בשכבת המבנים"]


@pytest.mark.asyncio
async def test_no_verdict_is_written_when_the_building_file_was_never_read(session):
    """״לא נמצא חידוש״ בלי היתרי תיק היה ״עבר״ שלא נבדק."""
    opp = await _parcel(session, "9923", **{**ANSWERED, "floors": 9})
    assert (await renewal.apply(session, opp))["status"] == "unknown"
    assert await _renewal_rows(session, opp.id) == []


@pytest.mark.asyncio
async def test_a_newer_team_decision_survives_apply_and_an_older_one_does_not(session, monkeypatch):
    opp = await _parcel(session, "9924", post_2005_permit=True, **{**ANSWERED, "floors": 7})
    await renewal.record_team_decision(session, opp, status="none", source="Street View",
                                       evidence_url="https://maps.example/x", note="בניין ישן",
                                       checked_by="team@x")
    assert (await renewal.apply(session, opp))["status"] == "none"      # גוברת על הסימנים

    later = {"block": "9924", "parcel": "1", "address": "x", "status": "verified_renewed",
             "source": "Street View", "evidence_url": None, "checked_by": "חן",
             "checked_at": (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat(),
             "note": None}
    monkeypatch.setattr(RS, "_manual", lambda: {"9924/1": later})
    assert (await renewal.apply(session, opp))["status"] == "verified_renewed"
    (row,) = await _renewal_rows(session, opp.id)
    assert row.method == renewal.LIST_METHOD


@pytest.mark.asyncio
async def test_delivery_answers_the_renewal_gate_from_the_database_without_the_archive(session):
    """תיק שכבר נקרא, בלי `renewal_status` — המצב של כל המסד לפני `apply_renewed`.
    המסירה משלימה את השער מהמסד; ‏conftest מפיל כל פנייה לארכיון."""
    from app.cities.herzliya.archive_facts import fetch_for_delivery
    c, u = await _company(session)
    opp = await _parcel(session, "9925", post_2005_permit=False, **ANSWERED)
    await refresh_one(session, HerzliyaCityRules(), opp.id)

    _, charged = await deliver(session, opp.id, c.id, u.id, on_unready=fetch_for_delivery)
    assert charged is True
    (row,) = await _renewal_rows(session, opp.id)
    assert row.value["status"] == "none"


@pytest.mark.asyncio
async def test_the_team_endpoint_records_a_decision_only_for_the_team(session):
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_async_session
    from app.core.security import get_jwt_strategy
    from app.main import app

    opp = await _parcel(session, "9926", post_2005_permit=True, renewal_status=SUSPECTED, **ANSWERED)
    await refresh_one(session, HerzliyaCityRules(), opp.id)
    c, customer = await _company(session)
    team = User(email=f"{uuid.uuid4().hex[:8]}@r.local", hashed_password="x", is_active=True,
                is_superuser=True, is_verified=True, full_name="צוות", role="member",
                company_id=c.id)
    session.add(team)
    await session.flush()
    body = {"status": "verified_renewed", "source": "Street View 17.09",
            "evidence_url": "https://maps.example/x", "note": "9 קומות חדשות"}
    url = f"/api/v1/candidates/herzliya/{opp.id}/renewal"

    app.dependency_overrides[get_async_session] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            async def as_(who, payload):
                token = await get_jwt_strategy().write_token(who)
                return await http.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            assert (await as_(customer, body)).status_code == 403
            assert (await as_(team, {**body, "evidence_url": ""})).status_code == 422
            r = await as_(team, body)
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert r.json()["renewal_status"] == "verified_renewed"
    assert r.json()["assessment"]["status"] == "ineligible"
    (row,) = await _renewal_rows(session, opp.id)
    assert row.certainty == Certainty.MANUALLY_VERIFIED.value and row.method == renewal.TEAM_METHOD


def test_the_dossier_shows_a_sentence_and_never_the_team_note():
    from app.cities.herzliya.dossier import _shown
    team_none = {"status": "none", "manual": True, "checked_by": "team@x",
                 "reasons": ["בדיקת צוות: Street View", "הערה פנימית"]}
    shown = _shown("renewal_status", team_none)
    assert shown == "נבדק ידנית: לא חודש ואינו בפרויקט חתום"
    assert _shown("renewal_status", NONE).endswith("לא נבדק בשטח")


# ── הסקריפט ──

async def _blind_parcel(session, block):
    """חלקה כפי שהיא במסד היום: `occupied` אמת מהקריאה העיוורת, בלי חידוש."""
    opp = await _parcel(session, block, post_2005_permit=True, **ANSWERED)
    await session.execute(select(FieldEvidence))           # autoflush
    for row in (await session.execute(select(FieldEvidence).where(
            FieldEvidence.opportunity_id == opp.id,
            FieldEvidence.field.in_(("strengthened", "occupied"))))).scalars():
        row.source_url = "https://handasi.complot.co.il/x"
        row.value = row.field == "occupied"
    await session.flush()
    return opp


@pytest.mark.asyncio
async def test_the_script_dry_run_writes_nothing(session, monkeypatch, capsys):
    sys.path.insert(0, str(SCRIPTS))
    import apply_renewed

    @asynccontextmanager
    async def same_session():
        yield session

    opp = await _blind_parcel(session, "9931")
    monkeypatch.setattr(apply_renewed, "AsyncSessionLocal", same_session)
    assert await apply_renewed.main(apply=False) == 1
    out = capsys.readouterr().out
    assert "הרצה יבשה" in out and "9931/1" in out and "חשוד" in out
    assert "strengthened/occupied" in out
    assert await _renewal_rows(session, opp.id) == []
    left = (await session.execute(select(FieldEvidence.field).where(
        FieldEvidence.opportunity_id == opp.id,
        FieldEvidence.field.in_(("strengthened", "occupied"))))).scalars().all()
    assert sorted(left) == ["occupied", "strengthened"]


@pytest.mark.asyncio
async def test_the_script_applies_and_retires_the_blind_rows(session, monkeypatch, capsys):
    sys.path.insert(0, str(SCRIPTS))
    import apply_renewed

    @asynccontextmanager
    async def same_session():
        yield session

    opp = await _blind_parcel(session, "9932")
    monkeypatch.setattr(apply_renewed, "AsyncSessionLocal", same_session)
    assert await apply_renewed.main(apply=True) == 0
    fields = {r.field: r for r in (await session.execute(select(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp.id))).scalars()}
    assert "strengthened" not in fields and "occupied" not in fields
    assert fields["tama38_event"].value is True
    assert fields["renewal_status"].value["status"] == "suspected"
    await session.refresh(opp)
    assert opp.metadata_json["assessment"]["under_review"] is True
