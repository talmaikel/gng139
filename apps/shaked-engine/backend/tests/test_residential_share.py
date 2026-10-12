"""‏W10 · #115 · יחס המגורים של §70א, מוזן מטבלת השטחים בגרמושקה.

השותפים שאלו איך יודעים שלפחות 70% מגורים. הבדיקות כאן על מה שנכשל בשקט:
הזנה של חברה אחת לתיק שלא נמסר לה, יחס שעובר בלי לומר על מה נשען, הזנה
שנייה שנערמת על הראשונה והופכת לסתירה, וקלט חסר-היגיון שמתקבל כמספר.
ובעיקר — מגרש שלא הוזן לו דבר נשאר בדיוק כמו היום: ״לא ידוע״, וניתן למסירה.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.cities.herzliya import rights
from app.cities.herzliya.assessments import refresh_one
from app.cities.herzliya.dossier import build
from app.cities.herzliya.rules import HerzliyaCityRules
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.evidence import Certainty
from app.main import app
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.package import Balance
from app.models.tenant import Company, User
from app.services.deliveries import deliver
from app.services.evidence_store import deciding, fields_for
from app.services.residential_share import record_ocr_candidate

SQUARE = ("MULTIPOLYGON(((34.8470000 32.1670000,34.8474000 32.1670000,"
          "34.8474000 32.1673000,34.8470000 32.1673000,34.8470000 32.1670000)))")

# כל שערי §70א נענו חוץ מה-70% — המצב של מגרש שהארכיון שלו נשלף
ANSWERED = dict(residential_zoning=True, permit_date="1978-01-01", strengthened=False,
                occupied=False, post_2005_permit=False, floors=4, units=28,
                scope_buildings=1, street_width=12.0,
                renewal_policy_category="התחדשות מגרשית מוטת מגורים",
                in_tama70=True, registration_area='שז"ר',
                # ‏W5 · בלי הכרעת חידוש מגרש אינו נמסר
                renewal_status={"status": "none", "reasons": [], "manual": False})

DRAWING = "https://archive.example.test/tik/123/gramushka.pdf"


async def _user(session, name="חברת שטחים"):
    c = Company(name=name, slug=f"w-{uuid.uuid4().hex[:8]}")
    session.add(c)
    await session.flush()
    session.add(Balance(company_id=c.id, credits_remaining=3))
    u = User(email=f"{uuid.uuid4().hex[:8]}@w.local", hashed_password="x", is_active=True,
             is_superuser=False, is_verified=True, full_name="בודק", role="member",
             company_id=c.id)
    session.add(u)
    await session.flush()
    return u


async def _delivered(session, user, block):
    """מגרש שנמסר לחברת המשתמש, בדרך האמיתית: הערכה ואז מסירה."""
    opp = Opportunity(city_code="herzliya", address=f"רחוב השטחים {block}", block=block,
                      block_suffix=0, parcel="1", geom=f"SRID=4326;{SQUARE}",
                      area_sqm=1800.0, existing_units=28,
                      verification_level=VerificationLevel.RAW.value, metadata_json={})
    session.add(opp)
    await session.flush()
    now = datetime.now(timezone.utc)
    for field, value in ANSWERED.items():
        session.add(FieldEvidence(
            opportunity_id=opp.id, field=field, value=value,
            certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
            retrieved_at=now - timedelta(days=1), location=f"גוש {block} חלקה 1"))
    await session.flush()
    await refresh_one(session, HerzliyaCityRules(), opp.id)
    await deliver(session, opp.id, user.company_id, user.id)
    return opp


@pytest.fixture
async def client(session):
    user = await _user(session)
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[current_active_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.user = user
        yield c
    app.dependency_overrides.clear()


def _body(residential, total, **extra):
    return {"residential_sqm": residential, "total_sqm": total, "source_url": DRAWING, **extra}


async def _manual_rows(session, opp):
    return (await session.execute(select(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp.id,
        FieldEvidence.field == "residential_share"))).scalars().all()


# ── ‏ACC-08 · רק למי שקיבל את התיק ──

@pytest.mark.asyncio
async def test_another_company_cannot_read_or_write_the_share(client, session):
    """‏404 כמו התיק עצמו — ‏403 היה מאשר שהמזהה קיים."""
    opp = await _delivered(session, client.user, "9701")
    other = await _user(session, "חברה אחרת")
    app.dependency_overrides[current_active_user] = lambda: other
    assert (await client.get(f"/api/v1/dossiers/{opp.id}/residential-share")).status_code == 404
    put = await client.put(f"/api/v1/dossiers/{opp.id}/residential-share", json=_body(820, 1000))
    assert put.status_code == 404
    assert await _manual_rows(session, opp) == []                 # ושום דבר לא נכתב

    app.dependency_overrides[current_active_user] = lambda: client.user
    unknown = await client.get(f"/api/v1/dossiers/{uuid.uuid4()}/residential-share")
    assert unknown.status_code == 404
    assert (await client.get(f"/api/v1/dossiers/{opp.id}/residential-share")).status_code == 200


# ── בלי הזנה: בדיוק כמו היום ──

@pytest.mark.asyncio
async def test_a_parcel_without_an_entry_stays_unknown_and_deliverable(client, session):
    opp = await _delivered(session, client.user, "9702")
    r = (await client.get(f"/api/v1/dossiers/{opp.id}/residential-share")).json()
    assert r["residential_share"] is None and r["entry"] is None
    assert r["gate"]["status"] == "unknown"
    assert "טבלת השטחים בהיתר" in r["gate"]["detail"] and "אומת" not in r["gate"]["detail"]
    assert r["assessment"]["deliverable"] is True
    assert opp.metadata_json["assessment"]["threshold_open"] == ["residential_share"]


# ── הזנה מכריעה, ואומרת על מה ──

@pytest.mark.asyncio
async def test_82_percent_from_the_area_table_passes_the_gate_and_says_why(client, session):
    opp = await _delivered(session, client.user, "9703")
    r = await client.put(f"/api/v1/dossiers/{opp.id}/residential-share",
                         json=_body(820, 1000, page="3"))
    assert r.status_code == 200
    body = r.json()
    assert body["residential_share"] == 0.82
    gate = body["gate"]
    assert gate["status"] == "passed"
    assert gate["detail"].startswith("82% מגורים לפי טבלת השטחים בהיתר")
    assert "עמ׳ 3" in gate["detail"] and "820 מתוך 1,000 מ״ר מגורים" in gate["detail"]
    assert gate["detail"].endswith("(אומת ידנית)")
    assert body["entry"]["source_url"] == DRAWING and body["entry"]["retrieved_at"]

    # הערך מכריע באמת — לא רק מוצג
    assert deciding(await fields_for(session, opp.id))["residential_share"] == 0.82
    stored = opp.metadata_json["assessment"]
    assert "residential_share" not in stored["threshold_open"]
    assert "residential_share" not in stored["blocking"]
    assert stored["deliverable"] is True

    # ומה שהלקוח רואה בתיק: השער אינו ברשימת ״אין מקור פתוח״, והראיה מכריעה
    d = await build(session, HerzliyaCityRules(), opp.id, client.user.company_id)
    assert "residential_share" not in {g["id"] for g in d["gaps"]["unobtainable"]}
    row = next(e for e in d["evidence"] if e["field"] == "residential_share")
    assert row["decides"] is True and row["certainty_label"] == "אומת ידנית"


@pytest.mark.asyncio
async def test_55_percent_fails_the_gate_with_the_same_basis(client, session):
    opp = await _delivered(session, client.user, "9704")
    body = (await client.put(f"/api/v1/dossiers/{opp.id}/residential-share",
                             json=_body(550, 1000))).json()
    assert body["gate"]["status"] == "failed"
    assert body["gate"]["detail"].startswith("55% מגורים לפי טבלת השטחים בהיתר")
    assert "(אומת ידנית)" in body["gate"]["detail"] and "פחות מ-70%" in body["gate"]["detail"]
    assert opp.metadata_json["assessment"]["status"] == "ineligible"
    assert opp.metadata_json["assessment"]["deliverable"] is False


@pytest.mark.asyncio
async def test_a_second_entry_replaces_the_first_rather_than_conflicting(client, session):
    """שתי שורות ידניות שונות היו סתירה, והשער היה חוזר ל״לא ידוע״ בשקט."""
    opp = await _delivered(session, client.user, "9705")
    url = f"/api/v1/dossiers/{opp.id}/residential-share"
    assert (await client.put(url, json=_body(820, 1000))).status_code == 200
    body = (await client.put(url, json=_body(550, 1000, note="קומת קרקע מסחרית"))).json()
    rows = await _manual_rows(session, opp)
    assert [r.value for r in rows] == [0.55]
    assert body["residential_share"] == 0.55 and body["gate"]["status"] == "failed"
    assert "הערה: קומת קרקע מסחרית" in body["entry"]["location"]


@pytest.mark.asyncio
async def test_an_entry_does_not_erase_a_different_kind_of_evidence(client, session):
    """רק ההזנה הידנית מוחלפת. קריאת מודל שחלוקה עליה נשארת — וזו סתירה אמיתית."""
    opp = await _delivered(session, client.user, "9706")
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="residential_share", value=0.9,
        certainty=Certainty.AI_CANDIDATE.value, source_url=DRAWING,
        retrieved_at=datetime.now(timezone.utc), location="עמ׳ 2"))
    await session.flush()
    body = (await client.put(f"/api/v1/dossiers/{opp.id}/residential-share",
                             json=_body(820, 1000))).json()
    assert len(await _manual_rows(session, opp)) == 2
    assert body["certainty"] == "conflict"
    assert body["residential_share"] is None and body["gate"]["status"] == "unknown"


# ── קלט חסר-היגיון נדחה, ואינו נכתב ──

@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    _body(0, 1000),
    _body(820, 0),
    _body(-5, 1000),
    _body(1200, 1000),                                   # מגורים יותר מהכול
    _body(820, 10_000_000),
    {"residential_sqm": 820, "total_sqm": 1000},        # בלי קישור לגרמושקה
    _body(820, 1000, source_url="גרמושקה"),
    _body(820, 1000, source_url="javascript:alert(1)"),
    _body(820, 1000, page="x" * 21),
    {"residential_sqm": "הרבה", "total_sqm": 1000, "source_url": DRAWING},
])
async def test_nonsense_input_is_refused(client, session, payload):
    opp = await _delivered(session, client.user, "9707")
    r = await client.put(f"/api/v1/dossiers/{opp.id}/residential-share", json=payload)
    assert r.status_code == 422
    assert await _manual_rows(session, opp) == []


# ── W10: המועמד האוטומטי (record_ocr_candidate) ──

@pytest.mark.asyncio
async def test_ocr_candidate_is_displayed_but_never_decides(client, session):
    opp = await _delivered(session, client.user, "9710")
    wrote = await record_ocr_candidate(
        session, opp.id, residential_sqm=820, total_sqm=1000,
        source_url=DRAWING, retrieved_at=None,
        location="טבלת השטחים בהיתר · עמ׳ 3", method="tesseract_regex")
    await session.commit()
    assert wrote is True

    r = (await client.get(f"/api/v1/dossiers/{opp.id}/residential-share")).json()
    assert r["residential_share"] is None            # לא מכריע
    assert r["gate"]["status"] == "unknown"           # השער עדיין לא ידוע
    assert r["entry"] is None                          # אין הזנה ידנית
    assert r["ocr_candidate"]["residential_share"] == 0.82   # אבל מוצג


@pytest.mark.asyncio
async def test_a_rerun_replaces_its_own_candidate_instead_of_piling_up(client, session):
    opp = await _delivered(session, client.user, "9711")
    await record_ocr_candidate(session, opp.id, residential_sqm=820, total_sqm=1000,
                               source_url=DRAWING, retrieved_at=None,
                               location="עמ׳ 3", method="tesseract_regex")
    await record_ocr_candidate(session, opp.id, residential_sqm=850, total_sqm=1000,
                               source_url=DRAWING, retrieved_at=None,
                               location="עמ׳ 3", method="tesseract_regex")
    await session.commit()
    rows = await _manual_rows(session, opp)
    ocr_rows = [r for r in rows if r.certainty == Certainty.OCR_CANDIDATE.value]
    assert len(ocr_rows) == 1 and ocr_rows[0].value == 0.85


@pytest.mark.asyncio
async def test_ocr_candidate_never_contests_an_already_decided_gate(client, session):
    """A person confirmed 82%; a later automated pass reading a different
    number must not turn that into a conflict."""
    opp = await _delivered(session, client.user, "9712")
    await client.put(f"/api/v1/dossiers/{opp.id}/residential-share", json=_body(820, 1000))
    wrote = await record_ocr_candidate(
        session, opp.id, residential_sqm=550, total_sqm=1000,
        source_url=DRAWING, retrieved_at=None, location="עמ׳ 3", method="tesseract_regex")
    await session.commit()
    assert wrote is False

    r = (await client.get(f"/api/v1/dossiers/{opp.id}/residential-share")).json()
    assert r["residential_share"] == 0.82 and r["gate"]["status"] == "passed"
    assert r["ocr_candidate"] is None


@pytest.mark.asyncio
async def test_a_manual_correction_clears_the_stale_candidate_it_replaces(client, session):
    """The review screen exists to correct the automatic reading -- a human
    typing a different number must decide outright, not end up in a
    conflict against the very candidate they were reviewing."""
    opp = await _delivered(session, client.user, "9713")
    await record_ocr_candidate(session, opp.id, residential_sqm=550, total_sqm=1000,
                               source_url=DRAWING, retrieved_at=None,
                               location="עמ׳ 3", method="tesseract_regex")
    await session.commit()

    body = (await client.put(f"/api/v1/dossiers/{opp.id}/residential-share",
                             json=_body(820, 1000))).json()
    assert body["residential_share"] == 0.82 and body["gate"]["status"] == "passed"
    assert body["certainty"] == "manually_verified"    # ולא "conflict"
    rows = await _manual_rows(session, opp)
    assert [r.certainty for r in rows] == [Certainty.MANUALLY_VERIFIED.value]  # ה-OCR נמחקה


@pytest.mark.asyncio
async def test_an_unrelated_ai_candidate_still_conflicts_with_a_manual_entry(client, session):
    """record() clears its own OCR_CANDIDATE, but an independent AI_CANDIDATE
    observation from elsewhere is a different kind of evidence -- disagreeing
    with it stays a real conflict (unchanged from before this feature)."""
    opp = await _delivered(session, client.user, "9714")
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="residential_share", value=0.9,
        certainty=Certainty.AI_CANDIDATE.value, source_url=DRAWING,
        retrieved_at=datetime.now(timezone.utc), location="עמ׳ 2"))
    await session.flush()
    body = (await client.put(f"/api/v1/dossiers/{opp.id}/residential-share",
                             json=_body(820, 1000))).json()
    assert body["certainty"] == "conflict"
    assert body["residential_share"] is None and body["gate"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_record_ocr_candidate_rejects_the_same_nonsense_as_the_endpoint(session):
    """`worker.py` calls this directly, with no request validation in front
    of it -- it has to reject a bad reading on its own."""
    with pytest.raises(ValueError):
        await record_ocr_candidate(
            session, uuid.uuid4(), residential_sqm=1200, total_sqm=1000,
            source_url=DRAWING, retrieved_at=None, location="עמ׳ 3", method="tesseract_regex")


# ── נוסח השער ──

def test_a_share_without_a_known_basis_does_not_claim_one():
    gate = next(c for c in rights.threshold_checks({"residential_share": 0.82})
                if c.id == "residential_share")
    assert gate.status == "passed" and gate.detail == "82% מגורים"


def test_a_failing_share_is_never_shown_as_seventy_percent():
    gate = next(c for c in rights.threshold_checks({"residential_share": 0.6996})
                if c.id == "residential_share")
    assert gate.status == "failed"
    assert gate.detail.startswith("69.9% מגורים")


def test_the_basis_names_the_place_and_whether_a_person_checked_it():
    loc = "טבלת השטחים בהיתר · עמ׳ 3 · 820 מתוך 1,000 מ״ר מגורים"
    assert rights.share_basis({"location": loc, "certainty": "manually_verified"}) \
        == f"לפי {loc} (אומת ידנית)"
    assert rights.share_basis({"location": loc, "certainty": "official"}) == f"לפי {loc}"
    assert rights.share_basis({"certainty": "manually_verified"}) is None
