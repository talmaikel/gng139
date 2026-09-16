"""כתיבת `renewal_status` כראיה. (W5 · #110)

שלושה מקורות, לפי סדר:

  1. **החלטת צוות** מהמסך (`record_team_decision`) — כל עוד היא חדשה
     מהבדיקה שברשימה.
  2. **הרשימה הידנית** `data/verified_renewed.json` — ‏MANUALLY_VERIFIED.
  3. **הסימנים** מתיק הבניין ומשכבת המבנים — ‏DERIVED.

סימנים שאין מולם היתרי תיק אינם נכתבים כלל: השער נשאר ״לא ידוע״ והמסירה
נחסמת, ולא נקראת כ״לא נמצא חידוש״.
"""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.cities.herzliya import renewal_signals as RS
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity
from app.services.evidence_store import deciding, fields_for

FIELD = "renewal_status"
LIST_URL = ("https://github.com/talmaikel/gng139/blob/main/apps/shaked-engine/backend/"
            "app/cities/herzliya/data/verified_renewed.json")
LIST_METHOD = "רשימה ידנית של בניינים שחודשו"
TEAM_METHOD = "החלטת צוות במסך המנהל"
SIGNAL_METHOD = "היתר אחרי 18.5.2005 ו-6+ קומות, בנוי/מגרש 2.5+ או מייצג; או תמ״א 38 בתיק"
# השדות שהחשד נשען עליהם. הראשונים מהתיק — מהם נלקח המקור.
ARCHIVE_INPUTS = ("post_2005_permit", "tama38_event", "representative_event")
LAYER_INPUTS = ("floors", "parcel_area")


def _at(opp: Opportunity) -> str:
    return f"גוש {opp.block} חלקה {opp.parcel}"


def signal_inputs(fields: dict[str, dict], area_sqm: float | None = None,
                  extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """הקלטים של `signals()` מתוך השדות המוכרעים.

    השטח הקיים הוא ESTIMATE ואינו מכריע דבר — אבל כאן הוא רק מעורר חשד
    ולעולם אינו מעביר שער, ולכן נקרא ישירות. ברוטו = הערך / k.
    """
    from app.cities.herzliya.seed_layer_a import K
    d = {**deciding(fields), **(extra or {})}
    est = (fields.get("existing_area") or {}).get("value")
    return dict(post_2005_permit=d.get("post_2005_permit"), floors=d.get("floors"),
                built_sqm=est / K if isinstance(est, (int, float)) else None,
                lot_sqm=d.get("parcel_area") or area_sqm,
                representative_event=d.get("representative_event"),
                tama38_event=d.get("tama38_event"))


def _team_is_newer(team: FieldEvidence, entry: dict | None) -> bool:
    if entry is None or not entry.get("checked_at") or team.retrieved_at is None:
        return True
    return team.retrieved_at.date() >= date.fromisoformat(entry["checked_at"])


def _row(opp: Opportunity, decision: dict, entry: dict | None,
         fields: dict[str, dict], now: datetime) -> dict[str, Any] | None:
    if entry is not None:
        return dict(field=FIELD, value=decision, certainty=Certainty.MANUALLY_VERIFIED.value,
                    source_url=entry.get("evidence_url") or LIST_URL, retrieved_at=now,
                    # מתי נבדק — שונה ממתי קראנו את הרשימה
                    source_updated_at=entry.get("checked_at"),
                    location=f'{_at(opp)} · {entry["source"]}', method=LIST_METHOD)
    if decision["status"] not in ("suspected", "none"):
        return None
    used = [fields[n] for n in ARCHIVE_INPUTS + LAYER_INPUTS
            if (fields.get(n) or {}).get("value") is not None and fields[n].get("source")]
    archive = next((fields[n] for n in ARCHIVE_INPUTS
                    if (fields.get(n) or {}).get("value") is not None
                    and (fields[n].get("source") or {}).get("url")), None)
    stamps = [f["source"]["retrieved_at"] for f in used if (f.get("source") or {}).get("retrieved_at")]
    if archive is None or not stamps:
        return None
    # הגיל של המסקנה הוא הגיל של הקלט הישן ביותר שלה
    return dict(field=FIELD, value=decision, certainty=Certainty.DERIVED.value,
                source_url=archive["source"]["url"],
                retrieved_at=datetime.fromisoformat(min(stamps)),
                location=f"{_at(opp)} · תיק הבניין ושכבת המבנים", method=SIGNAL_METHOD)


async def plan(session, opp: Opportunity, *, now: datetime | None = None,
               extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """מה ייכתב, בלי לכתוב. ‏`extra` — שדות שעוד לא במסד (הרצה יבשה)."""
    now = now or datetime.now(timezone.utc)
    await session.flush()                   # שורות תיק שנוספו זה עתה
    existing = (await session.execute(
        select(FieldEvidence).where(FieldEvidence.opportunity_id == opp.id,
                                    FieldEvidence.field == FIELD))).scalars().all()
    team = max((r for r in existing if r.method == TEAM_METHOD),
               key=lambda r: r.retrieved_at or now, default=None)
    entry = RS.manual_entry(opp.block, opp.parcel)
    if team is not None and _team_is_newer(team, entry):
        return {"decision": team.value, "row": None, "keep_team": True, "existing": existing}
    fields = await fields_for(session, opp.id)
    decision = RS.decide(entry, RS.signals(**signal_inputs(fields, opp.area_sqm, extra)))
    return {"decision": decision, "row": _row(opp, decision, entry, fields, now),
            "keep_team": False, "existing": existing}


async def apply(session, opp: Opportunity, *, now: datetime | None = None,
                plan_: dict[str, Any] | None = None) -> dict[str, Any]:
    """כותב את ההכרעה במקום כל שורה קודמת. אינו עושה commit."""
    p = plan_ or await plan(session, opp, now=now)
    if p["keep_team"]:
        return p["decision"]
    await session.execute(delete(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp.id, FieldEvidence.field == FIELD))
    if p["row"]:
        session.add(FieldEvidence(opportunity_id=opp.id, **p["row"]))
    await session.flush()
    return p["decision"]


async def record_team_decision(session, opp: Opportunity, *, status: str, source: str,
                               evidence_url: str, note: str | None, checked_by: str | None,
                               now: datetime | None = None) -> dict[str, Any]:
    """אישור או פסילה של הצוות. ‏`checked_by` נשמר בערך ואינו מוצג ללקוח."""
    if status not in RS.STATUSES:
        raise ValueError(f"סטטוס {status!r}")
    now = now or datetime.now(timezone.utc)
    value = {"status": status, "manual": True, "checked_by": checked_by,
             "reasons": [f"בדיקת צוות: {source}", *([note] if note else [])]}
    await session.execute(delete(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp.id, FieldEvidence.field == FIELD))
    session.add(FieldEvidence(
        opportunity_id=opp.id, field=FIELD, value=value,
        certainty=Certainty.MANUALLY_VERIFIED.value, source_url=evidence_url,
        retrieved_at=now, location=f"{_at(opp)} · {source}"[:400], method=TEAM_METHOD))
    await session.flush()
    return value


async def apply_all(session, city_code: str = "herzliya", *, write: bool = True,
                    now: datetime | None = None,
                    extra_for: dict | None = None) -> dict[str, Any]:
    """כל ההזדמנויות בעיר. ‏`write=False` — רק מה היה נכתב, בלי לגעת במסד.

    ‏`extra_for` — לפי מזהה הזדמנות, שדות שהרצה יבשה מניחה שכבר נכתבו.
    """
    now = now or datetime.now(timezone.utc)
    opps = (await session.execute(
        select(Opportunity).where(Opportunity.city_code == city_code)
        .order_by(Opportunity.block, Opportunity.parcel))).scalars().all()
    counts = {s: 0 for s in (*RS.STATUSES, "unknown")}
    counts.update(team_kept=0, manual=0, changed=0)
    flagged, by_key = [], {}
    for opp in opps:
        p = await plan(session, opp, now=now, extra=(extra_for or {}).get(opp.id))
        decision = p["decision"]
        before = sorted(str((r.value or {}).get("status")) for r in p["existing"])
        if write:
            await apply(session, opp, now=now, plan_=p)
        status = decision.get("status") or "unknown"
        by_key[f"{opp.block}/{opp.parcel}"] = status
        counts[status] = counts.get(status, 0) + 1
        counts["team_kept"] += 1 if p["keep_team"] else 0
        counts["manual"] += 1 if decision.get("manual") else 0
        # שינוי בסטטוס מול מה שבמסד — לא בכל שורה שנכתבת מחדש
        counts["changed"] += 0 if before == ([status] if p["row"] or p["keep_team"] else []) else 1
        if status in ("verified_renewed", "suspected"):
            flagged.append({"key": f"{opp.block}/{opp.parcel}", "address": opp.address,
                            "status": status, "manual": bool(decision.get("manual")),
                            "reasons": decision.get("reasons") or []})
    return {"counts": counts, "flagged": flagged, "by_key": by_key, "total": len(opps)}
