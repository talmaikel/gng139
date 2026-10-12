"""‏W5 · חיפוש אינטרנט אוטומטי לחלוטין לאיתור בניין שכבר חודש — האורכסטרציה.

מבטל את הדרישה הקודמת לבדיקת Street View ואישור צוות (בועז, 16.09 →
בועז/הצוות, זו החלטה): **חלקה חדשה נבדקת אוטומטית בלבד**, ותוצאה ודאית
פוסלת מיד בלי מסך אישור. הרשימה הידנית (`renewal_signals.load_manual`)
נשארת לרשומות היסטוריות, אבל אין להוסיף אליה עוד.

שלושה מודולים, שלוש אחריות, בלי לערבב:

  * ``renewal_search_provider`` — הרשת: ‏`WebSearchProvider`, ‏`BraveSearchProvider`.
  * ``renewal_search_signals``  — טהור: נרמול כתובת, סיווג תוצאות.
  * **הקובץ הזה**              — קושר את השניים, כותב ראיה, ומריץ backfill.

הכתיבה למסד היא לשדה נפרד — ``renewal_web_search`` — לא ישירות ל-
‏`renewal_status`. השילוב בהכרעה הסופית הוא ב-`renewal_signals.decide()`
דרך `renewal.plan()`, בדיוק כמו ש-`post_2005_permit`/`tama38_event`
(מתיק הבניין) הם קלט ל-`renewal_signals.signals()` ולא ההכרעה עצמה.

**מטמון ולא חיפוש בכל רענון:** ‏`enrich()` בודק אם כבר יש ראיה טרייה
(אותו חלון גיל שכל שדה אחר משתמש בו — ‏`source_max_age_days`, ‏#config)
לפני שהוא פונה לרשת. בדיקה שלא הסתיימה (``retryable``) תמיד נבדקת שוב.
"""
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.cities.herzliya import renewal
from app.cities.herzliya.renewal_search_provider import (
    BraveSearchProvider,
    RenewalSearchUnavailable,
    WebSearchProvider,
)
from app.cities.herzliya.renewal_search_signals import (
    NO_SIGNAL,
    ClassificationOutcome,
    NormalizedAddress,
    classify_renewal_result,
    normalize_address,
)
from app.core.config import get_settings
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

FIELD = "renewal_web_search"
METHOD = "חיפוש אינטרנט אוטומטי (Brave Search API)"
PROVIDER_NAME = "brave"
CITY = "הרצליה"
SOURCE_DOC_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_SHORTLIST = 25  # כמו archive_facts.MAX_SHORTLIST — לא סריקה, ריצה מבוקרת

_ADDRESS_TAIL = re.compile(r"^(?P<street>.+?)\s+(?P<number>\d+(?:[-‐-―]\d+)?[א-ת]?)\s*$")


def parse_address(address: str | None) -> tuple[str | None, str | None]:
    """"<רחוב> <מספר>" מכתובת חופשית. בלי מספר בסוף — הרחוב מוחזר לבדו, בלי מספר."""
    if not address:
        return None, None
    m = _ADDRESS_TAIL.match(address.strip())
    return (m.group("street"), m.group("number")) if m else (address.strip(), None)


def build_queries(normalized: NormalizedAddress) -> list[str]:
    """כתובת מדויקת במרכאות, וגם שאילתה ממוקדת לתוצאות פרויקט במדלן."""
    address_phrase = f"{normalized.street} {normalized.house_number_raw}".strip()
    exact = f'"{address_phrase}" {normalized.city}'.strip()
    madlan = f'site:madlan.co.il/projects "{address_phrase}" {normalized.city}'.strip()
    return [exact, madlan]


def _evidence(normalized: NormalizedAddress, query: str, outcome: ClassificationOutcome,
             *, checked_at: datetime) -> dict[str, Any]:
    return {"status": outcome.status, "provider": PROVIDER_NAME, "query": query,
            "normalized_address": normalized.display, "matched_keyword": outcome.matched_keyword,
            "result_title": outcome.result_title, "result_url": outcome.result_url,
            "address_match_score": outcome.address_match_score, "reason": outcome.reason,
            "checked_at": checked_at.isoformat()}


async def check_address(provider: WebSearchProvider, street: str, house_number: str, city: str = CITY,
                        *, now: datetime | None = None) -> dict[str, Any]:
    """בדיקה אחת: נרמול, שתי שאילתות, וסיווג. אינה כותבת דבר במסד.

    שאילתה ששגתה אינה מפילה את הבדיקה כל עוד שאילתה אחרת הצליחה — רק אם
    **אף שאילתה** לא הסתיימה, התוצאה `retryable`.
    """
    now = now or datetime.now(timezone.utc)
    normalized = normalize_address(street, house_number, city)
    queries = build_queries(normalized)
    any_success, last_error = False, None
    for query in queries:
        try:
            results = await provider.search(query)
        except RenewalSearchUnavailable as exc:
            last_error = str(exc)
            continue
        any_success = True
        outcome = classify_renewal_result(normalized, results)
        if outcome.status == "verified_renewed":
            return _evidence(normalized, query, outcome, checked_at=now)
    if not any_success:
        return {"status": "retryable", "provider": PROVIDER_NAME, "query": queries[0],
                "normalized_address": normalized.display, "error": last_error,
                "checked_at": now.isoformat()}
    return _evidence(normalized, queries[0], NO_SIGNAL, checked_at=now)


async def check_parcel(provider: WebSearchProvider, addresses: list[tuple[str, str, str]],
                       *, now: datetime | None = None) -> dict[str, Any]:
    """כמה כתובות לאותה חלקה (חלקת פינה, למשל) — התאמה באחת פוסלת את כולה."""
    outcomes = [await check_address(provider, street, number, city, now=now)
                for street, number, city in addresses]
    verified = next((o for o in outcomes if o["status"] == "verified_renewed"), None)
    if verified is not None:
        return verified
    clean = next((o for o in outcomes if o["status"] == "no_automated_renewal_signal"), None)
    return clean if clean is not None else outcomes[0]


async def _existing_row(session, opportunity_id: UUID) -> FieldEvidence | None:
    rows = (await session.execute(select(FieldEvidence).where(
        FieldEvidence.opportunity_id == opportunity_id, FieldEvidence.field == FIELD))).scalars().all()
    return rows[0] if rows else None


def _needs_check(row: FieldEvidence | None, now: datetime) -> bool:
    """אין ראיה, הבדיקה הקודמת לא הסתיימה, או שהיא פגה — אותו חלון גיל
    שכל שדה מכריע אחר משתמש בו (`usable()`, ‏`source_max_age_days`)."""
    if row is None:
        return True
    if (row.value or {}).get("status") == "retryable":
        return True
    if row.retrieved_at is None:
        return True
    age_days = (now - row.retrieved_at).total_seconds() / 86400
    return age_days > get_settings().source_max_age_days


async def _write(session, opportunity_id: UUID, outcome: dict[str, Any], now: datetime) -> None:
    await session.execute(delete(FieldEvidence).where(
        FieldEvidence.opportunity_id == opportunity_id, FieldEvidence.field == FIELD))
    location = f'{outcome.get("normalized_address")} · {outcome.get("query")}'[:400]
    session.add(FieldEvidence(
        opportunity_id=opportunity_id, field=FIELD, value=outcome, certainty=Certainty.DERIVED.value,
        source_url=outcome.get("result_url") or SOURCE_DOC_URL, retrieved_at=now,
        location=location, method=METHOD))


async def enrich(session, opportunity_ids: list[UUID], provider: WebSearchProvider | None = None,
                 *, now: datetime | None = None) -> dict[str, Any]:
    """בודק ומעדכן `renewal_web_search` לכל הזדמנות ברשימה שאין לה ראיה
    טרייה, ומריץ `renewal.apply()` אחריה. ‏`write=False` אין — כמו הארכיון,
    זו קריאת רשת אמיתית, ומחליטים על ההרצה שלה מראש, לא בקריאה יבשה.
    """
    if len(opportunity_ids) > MAX_SHORTLIST:
        raise ValueError(f"{len(opportunity_ids)} הזדמנויות — מעל {MAX_SHORTLIST} לריצה אחת")
    now = now or datetime.now(timezone.utc)
    own_provider = provider is None
    provider = provider or BraveSearchProvider()
    counts = {"checked": 0, "skipped_fresh": 0, "skipped_no_address": 0,
              "verified_renewed": 0, "no_automated_renewal_signal": 0, "retryable": 0}
    try:
        for oid in opportunity_ids:
            opp = await session.get(Opportunity, oid)
            if opp is None:
                continue
            existing = await _existing_row(session, oid)
            if not _needs_check(existing, now):
                counts["skipped_fresh"] += 1
                continue
            street, number = parse_address(opp.address)
            if not street or not number:
                counts["skipped_no_address"] += 1
                continue
            outcome = await check_address(provider, street, number, now=now)
            await _write(session, oid, outcome, now)
            counts["checked"] += 1
            counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1
            await renewal.apply(session, opp, now=now)
        await session.flush()
    finally:
        if own_provider:
            await provider.close()
    return counts
