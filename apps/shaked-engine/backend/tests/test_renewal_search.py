"""‏W5 · חיפוש אינטרנט אוטומטי לחלוטין לאיתור בניין שכבר חודש. (#127)

בלי בדיקה ידנית, בלי Street View ובלי מסך אישור צוות: תוצאה ודאית מהחיפוש
פוסלת מיד, ובדיקה שלא הסתיימה חוסמת מסירה עד הרצה חוזרת. אף בדיקה כאן לא
פונה לרשת אמיתית — `never_reach_brave_search` ב-conftest אוכפת את זה על כל
הסוויטה, ו-`FakeSearchProvider` כאן מזריק תוצאות קבועות מראש.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.cities.herzliya import renewal, renewal_search as rsearch
from app.cities.herzliya import renewal_signals as RS
from app.cities.herzliya.assessments import refresh_one
from app.cities.herzliya.renewal_search_provider import RenewalSearchResult, RenewalSearchUnavailable
from app.cities.herzliya.renewal_search_signals import classify_renewal_result, normalize_address
from app.cities.herzliya.rules import HerzliyaCityRules
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel

GEOM = ("MULTIPOLYGON(((34.8105000 32.1605000,34.8109000 32.1605000,"
        "34.8109000 32.1608000,34.8105000 32.1608000,34.8105000 32.1605000)))")


def R(title: str = "", description: str = "", url: str = "") -> RenewalSearchResult:
    return RenewalSearchResult(title=title, description=description, url=url)


class FakeSearchProvider:
    """מזרקים אותו במפורש בכל בדיקה — שום קריאה אמיתית ל-Brave (#14)."""

    def __init__(self, results: list[RenewalSearchResult] | None = None,
                by_query: dict[str, list[RenewalSearchResult]] | None = None,
                fail: bool = False, fail_substrings: tuple[str, ...] = ()):
        self.default_results = results or []
        self.by_query = by_query or {}
        self.fail = fail
        self.fail_substrings = fail_substrings
        self.calls: list[str] = []

    async def search(self, query: str) -> list[RenewalSearchResult]:
        self.calls.append(query)
        if self.fail or any(s in query for s in self.fail_substrings):
            raise RenewalSearchUnavailable("מדומה בבדיקה: אין תשובה")
        return self.by_query.get(query, self.default_results)


async def _parcel(session, block, *, address="יגאל אלון 6", parcel="1"):
    opp = Opportunity(city_code="herzliya", address=address, block=block, block_suffix=0,
                      parcel=parcel, geom=f"SRID=4326;{GEOM}", area_sqm=1100.0, existing_units=28,
                      verification_level=VerificationLevel.RAW.value,
                      metadata_json={"category": "primary_candidate"})
    session.add(opp)
    await session.flush()
    return opp


ANSWERED = dict(residential_zoning=True, permit_date="1972-01-01", strengthened=False,
                occupied=False, floors=4, units=28, scope_buildings=1, parcel_area=1100.0,
                street_width=12.0, renewal_policy_category="התחדשות מגרשית מוטת מגורים",
                in_tama70=True, registration_area='שז"ר')


# ── #1-3, #6-8 · סיווג טהור: כתובת + מילת מפתח ──────────────────────────

def test_1_exact_address_and_title_tama38_disqualifies():
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title='פרויקט תמ"א 38 חדש ברחוב יגאל אלון 6, הרצליה',
                                        url="https://example.test/a")])
    assert out.status == "verified_renewed"
    assert "תמ" in out.matched_keyword
    assert "יגאל אלון 6" in out.reason and "הרצליה" in out.reason


def test_2_exact_address_and_description_strengthening_disqualifies():
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title="יגאל אלון 6, הרצליה",
                                        description="פרויקט חיזוק ותוספת בבניין הישן",
                                        url="https://example.test/b")])
    assert out.status == "verified_renewed" and out.matched_keyword == "חיזוק ותוספת"


def test_3_exact_address_and_madlan_project_page_disqualifies():
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title="יגאל אלון 6, הרצליה — דף פרויקט",
                                        url="https://www.madlan.co.il/projects/some-project-6")])
    assert out.status == "verified_renewed"
    assert "מדלן" in out.matched_keyword


def test_4_same_street_different_house_number_does_not_disqualify():
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title='תמ"א 38 ברחוב יגאל אלון 45, הרצליה',
                                        url="https://example.test/c")])
    assert out.status == "no_automated_renewal_signal"


def test_5_same_number_different_city_does_not_disqualify():
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title='תמ"א 38 ברחוב יגאל אלון 6, רמת גן',
                                        url="https://example.test/d")])
    assert out.status == "no_automated_renewal_signal"


@pytest.mark.parametrize("phrase", [
    'לא במסגרת תמ"א 38',
    'אינו פרויקט תמ"א',
    'ללא תמ"א 38',
])
def test_6_negated_wording_does_not_disqualify(phrase):
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title="יגאל אלון 6, הרצליה",
                                        description=phrase, url="https://example.test/e")])
    assert out.status == "no_automated_renewal_signal"


def test_7_result_without_a_renewal_keyword_does_not_disqualify():
    n = normalize_address("יגאל אלון", "6", "הרצליה")
    out = classify_renewal_result(n, [R(title="יגאל אלון 6, הרצליה — דירה למכירה",
                                        description="דירת 4 חדרים משופצת", url="https://example.test/f")])
    assert out.status == "no_automated_renewal_signal"


@pytest.mark.asyncio
async def test_8_no_results_at_all_is_no_automated_renewal_signal():
    provider = FakeSearchProvider(results=[])
    out = await rsearch.check_address(provider, "יגאל אלון", "6")
    assert out["status"] == "no_automated_renewal_signal"


# ── #9-12 · האורכסטרציה: timeout, כמה כתובות, שתי הכתובות האמיתיות ──────

@pytest.mark.asyncio
async def test_9_api_timeout_is_retryable_and_blocks_nothing_as_clean():
    provider = FakeSearchProvider(fail=True)
    out = await rsearch.check_address(provider, "יגאל אלון", "6")
    assert out["status"] == "retryable" and out.get("error")


@pytest.mark.asyncio
async def test_10_multiple_addresses_for_one_parcel_a_match_in_one_disqualifies_all():
    provider = FakeSearchProvider(by_query={
        '"הנדיב 45" הרצליה': [],
        'site:madlan.co.il/projects "הנדיב 45" הרצליה': [],
        '"רוטשילד 3" הרצליה': [R(title='תמ"א 38 ברחוב רוטשילד 3, הרצליה', url="https://example.test/g")],
        'site:madlan.co.il/projects "רוטשילד 3" הרצליה': [],
    })
    out = await rsearch.check_parcel(provider, [("הנדיב", "45", "הרצליה"), ("רוטשילד", "3", "הרצליה")])
    assert out["status"] == "verified_renewed"


@pytest.mark.asyncio
async def test_11_alon_yigal_6_is_identified_and_disqualified_by_a_project_result():
    provider = FakeSearchProvider(by_query={
        'site:madlan.co.il/projects "אלוף יגאל אלון 6" הרצליה': [
            R(title="פרויקט התחדשות — אלוף יגאל אלון 6, הרצליה",
              url="https://www.madlan.co.il/projects/alon-yigal-6"),
        ],
    })
    out = await rsearch.check_address(provider, "אלוף יגאל אלון", "6")
    assert out["status"] == "verified_renewed"
    assert out["result_url"].startswith("https://www.madlan.co.il/projects/")


@pytest.mark.asyncio
async def test_12_alon_yigal_2_is_checked_by_the_same_automated_mechanism():
    provider = FakeSearchProvider(results=[
        R(title="אלוף יגאל אלון 2, הרצליה — דירת 3 חדרים", url="https://example.test/h"),
    ])
    out = await rsearch.check_address(provider, "אלוף יגאל אלון", "2")
    assert out["status"] == "no_automated_renewal_signal"
    assert '"אלוף יגאל אלון 2" הרצליה' in provider.calls


# ── ההכרעה המשולבת (renewal_signals.decide/combine_with_search) ────────

def test_search_verified_overrides_clean_signals_and_no_archive_at_all():
    search = {"status": "verified_renewed", "reason": "נמצא אוטומטית תמ\"א 38 בכתובת יגאל אלון 6, הרצליה"}
    out = RS.decide(None, {"status": "none", "reasons": []}, search)
    assert out["status"] == "verified_renewed" and out["manual"] is False
    assert search["reason"] in out["reasons"]


def test_search_verified_overrides_a_none_signal_even_without_permit_data():
    search = {"status": "verified_renewed", "reason": "x"}
    out = RS.decide(None, RS.signals(post_2005_permit=None, floors=None, built_sqm=None, lot_sqm=None), search)
    assert out["status"] == "verified_renewed"


def test_search_no_signal_does_not_touch_a_suspected_signal():
    search = {"status": "no_automated_renewal_signal"}
    signal = {"status": "suspected", "reasons": ["7 קומות בשכבת המבנים"]}
    assert RS.decide(None, signal, search) == {**signal, "manual": False}


def test_retryable_search_downgrades_a_clean_signal_to_unknown():
    search = {"status": "retryable", "error": "timeout"}
    out = RS.decide(None, {"status": "none", "reasons": []}, search)
    assert out["status"] == "unknown"


def test_retryable_search_does_not_touch_an_existing_suspicion():
    search = {"status": "retryable", "error": "timeout"}
    signal = {"status": "suspected", "reasons": ["7 קומות בשכבת המבנים"]}
    out = RS.decide(None, signal, search)
    assert out["status"] == "suspected"


def test_the_manual_list_still_wins_over_an_automated_search_match():
    entry = {"status": "suspected", "source": "issue #101", "note": None, "checked_by": None, "checked_at": None}
    search = {"status": "verified_renewed", "reason": "x"}
    out = RS.decide(entry, {"status": "none", "reasons": []}, search)
    assert out["status"] == "suspected" and out["manual"] is True


def test_decide_without_a_search_argument_still_works():
    assert RS.decide(None, {"status": "none", "reasons": []})["status"] == "none"


# ── DB: הכתיבה, השער, והמסירה (#13) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_13_a_search_verified_parcel_is_ineligible_not_delivered_and_not_charged(session):
    from app.cities.herzliya.rights import renewal_check

    opp = await _parcel(session, "9950", address="יגאל אלון 6")
    for field, value in ANSWERED.items():
        session.add(FieldEvidence(opportunity_id=opp.id, field=field, value=value,
                                  certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
                                  retrieved_at=datetime.now(timezone.utc) - timedelta(days=1),
                                  location="בדיקה"))
    await session.flush()

    provider = FakeSearchProvider(by_query={
        '"יגאל אלון 6" הרצליה': [],
        'site:madlan.co.il/projects "יגאל אלון 6" הרצליה': [
            R(title="פרויקט התחדשות — יגאל אלון 6, הרצליה", url="https://www.madlan.co.il/projects/x"),
        ],
    })
    out = await rsearch.enrich(session, [opp.id], provider)
    assert out["verified_renewed"] == 1

    (row,) = (await session.execute(select(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp.id, FieldEvidence.field == "renewal_status"))).scalars().all()
    assert row.value["status"] == "verified_renewed" and row.value["manual"] is False
    assert row.certainty == Certainty.DERIVED.value          # לא MANUALLY_VERIFIED — ראיה אוטומטית
    assert renewal_check(row.value).status == "failed"

    a = await refresh_one(session, HerzliyaCityRules(), opp.id)
    assert a["status"] == "ineligible" and a["deliverable"] is False

    rows = await HerzliyaCityRules().screen_candidates(session, {"polygon": {
        "type": "Polygon", "coordinates": [[[34.8100, 32.1600], [34.8120, 32.1600],
                                            [34.8120, 32.1615], [34.8100, 32.1615],
                                            [34.8100, 32.1600]]]}})
    assert str(opp.id) not in {r["id"] for r in rows}       # לא ב-found


@pytest.mark.asyncio
async def test_13b_a_search_verified_parcel_is_refused_at_delivery_without_charging(session):
    from app.services.deliveries import NotDeliverable, deliver
    from app.models.package import Balance
    from app.models.tenant import Company, User
    import uuid

    opp = await _parcel(session, "9954", address="יגאל אלון 6")
    for field, value in ANSWERED.items():
        session.add(FieldEvidence(opportunity_id=opp.id, field=field, value=value,
                                  certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
                                  retrieved_at=datetime.now(timezone.utc) - timedelta(days=1),
                                  location="בדיקה"))
    await session.flush()
    provider = FakeSearchProvider(by_query={
        '"יגאל אלון 6" הרצליה': [],
        'site:madlan.co.il/projects "יגאל אלון 6" הרצליה': [
            R(title="פרויקט התחדשות — יגאל אלון 6, הרצליה", url="https://www.madlan.co.il/projects/y"),
        ],
    })
    await rsearch.enrich(session, [opp.id], provider)
    await refresh_one(session, HerzliyaCityRules(), opp.id)

    company = Company(name="חברת בדיקה", slug=f"t-{uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    session.add(Balance(company_id=company.id, credits_remaining=3))
    user = User(email=f"{uuid.uuid4().hex[:8]}@t.local", hashed_password="x", is_active=True,
               is_superuser=False, is_verified=True, full_name="בודק", role="member",
               company_id=company.id)
    session.add(user)
    await session.flush()

    calls = []

    async def fetch(s, oid):
        calls.append(oid)
        return True

    with pytest.raises(NotDeliverable):
        await deliver(session, opp.id, company.id, user.id, on_unready=fetch)
    assert calls == []
    credits = (await session.execute(select(Balance.credits_remaining)
                                     .where(Balance.company_id == company.id))).scalar_one()
    assert credits == 3


@pytest.mark.asyncio
async def test_a_retryable_search_blocks_delivery_even_when_the_archive_is_clean(session):
    opp = await _parcel(session, "9951", address="הנדיב 1")
    for field, value in ANSWERED.items():
        session.add(FieldEvidence(opportunity_id=opp.id, field=field, value=value,
                                  certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
                                  retrieved_at=datetime.now(timezone.utc) - timedelta(days=1),
                                  location="בדיקה"))
    session.add(FieldEvidence(opportunity_id=opp.id, field="post_2005_permit", value=False,
                              certainty=Certainty.DERIVED.value,
                              source_url="https://handasi.complot.co.il/x",
                              retrieved_at=datetime.now(timezone.utc) - timedelta(days=1), location="תיק"))
    await session.flush()

    provider = FakeSearchProvider(fail=True)
    out = await rsearch.enrich(session, [opp.id], provider)
    assert out["retryable"] == 1

    a = await refresh_one(session, HerzliyaCityRules(), opp.id)
    assert a["deliverable"] is False and "not_renewed" in a["threshold_open"]


@pytest.mark.asyncio
async def test_a_fresh_search_result_is_not_re_fetched_on_the_next_screen_refresh(session):
    """#אין לבצע מספר חיפושי רשת חוזרים בכל רענון מסך."""
    opp = await _parcel(session, "9952", address="הנדיב 1")
    provider = FakeSearchProvider(results=[])
    await rsearch.enrich(session, [opp.id], provider)
    assert len(provider.calls) == 2                          # שתי השאילתות, פעם אחת

    await rsearch.enrich(session, [opp.id], provider)
    assert len(provider.calls) == 2                          # לא נשאל שוב — הראיה עדיין טרייה


@pytest.mark.asyncio
async def test_a_retryable_search_is_retried_on_the_next_backfill(session):
    opp = await _parcel(session, "9953", address="הנדיב 1")
    failing = FakeSearchProvider(fail=True)
    await rsearch.enrich(session, [opp.id], failing)

    working = FakeSearchProvider(results=[])
    out = await rsearch.enrich(session, [opp.id], working)
    assert out["checked"] == 1 and out["no_automated_renewal_signal"] == 1
