import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.base import BaseCityRules, UnificationResult
from app.cities.herzliya.candidates import screen_herzliya_candidates
from app.cities.herzliya.unification import check_unification
from app.cities.herzliya import policy_envelope, rights
from app.cities.herzliya.xplan_schema import is_eligible_residential_code
from app.geo import itm
from app.models.opportunity import Opportunity
from app.services.evidence_store import deciding, fields_for, stale_fields

# Herzliya's minimum combined plot area for a "Shaked Alternative" urban-renewal lot.
HERZLIYA_MINIMUM_PLOT_AREA_SQM = 1000.0


class HerzliyaCityRules(BaseCityRules):
    city_code = "herzliya"
    display_name = "Herzliya"

    async def screen_candidates(self, session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
        return await screen_herzliya_candidates(session, filters)

    def is_eligible_xplan_code(self, xplan_code: str) -> bool:
        try:
            return is_eligible_residential_code(int(xplan_code))
        except (TypeError, ValueError):
            return False

    async def check_plot_unification(self, session: AsyncSession, parcel_ids: list[str]) -> UnificationResult:
        return await check_unification(session, parcel_ids, self.minimum_plot_area_sqm())

    def minimum_plot_area_sqm(self) -> float:
        return HERZLIYA_MINIMUM_PLOT_AREA_SQM

    async def assess(self, session: AsyncSession, opportunity_id) -> dict[str, Any]:
        """שרשרת הזכויות על הזדמנות אחת, מהראיות השמורות.

        רק שדות שרשאים להכריע נכנסים לשערים. `existing_area` נקרא בנפרד
        **בכוונה**: הוא ESTIMATE ולכן אינו מכריע דבר, אבל תקרת ה-400% היא
        חישוב ולא שער, ולכן היא מוצגת עם הסייג שלה ואינה פוסלת איש.
        """
        f = await fields_for(session, opportunity_id)
        d = deciding(f)

        checks = rights.threshold_checks(d)
        checks.append(_scope_check(d.get("scope_buildings")))

        # שורה חסרה (זריעה שקדמה ל-frontages_v2) אינה ״לא מאומת״ — היא ההתנהגות הקודמת.
        r = rights.floors(d.get("street_width"), d.get("renewal_policy_category"),
                          verified=d.get("street_width_verified") is not False,
                          narrow=d.get("street_narrow_frontages"))
        checks += r.checks

        est = f.get("existing_area") or {}
        # ההחרגה של §70ב(א)(1)(ב) נגזרת מהתיק. הראיה נושאת True/False ולא
        # שטח, כי התיק מדווח שהיתר ניתן ולא כמה מ״ר הוא הוסיף.
        post_2005 = (f.get("post_2005_permit") or {}).get("value")
        cap, cap_why = rights.cap_400(est.get("value"), post_2005)

        out: dict[str, Any] = {
            "checks": [c.__dict__ for c in checks],
            "status": _status(checks),
            "floors": {"low": r.floors_low, "high": r.floors_high,
                       "certain": r.floors_certain, "case_by_case": r.case_by_case},
            "cap_400_sqm": cap,
            "cap_400_basis": cap_why,
            "cap_400_certainty": est.get("certainty"),
            "cap_400_reliable": rights.cap_400_reliable(post_2005),
            "notes": list(r.notes),
            "stale_fields": stale_fields(f),
            # מה שהצוות צריך לראות במסך, בלי לפתוח את השער (W5)
            "renewal": _renewal(d.get("renewal_status")),
        }

        # ‏W1 · כמה מהתקרה נכנס בפועל לפי המדיניות. 400% הוא תקרה בחוק ולא זכות,
        # ובלי זה התיק חישב רווח על שטח שלא ייבנה.
        geo = (await session.execute(select(func.ST_AsGeoJSON(Opportunity.geom))
                                     .where(Opportunity.id == opportunity_id))).scalar_one_or_none()
        policy, policy_why = policy_envelope.compute(
            itm(json.loads(geo)) if geo else None,
            plot_sqm=(f.get("parcel_area") or {}).get("value"),
            floors_low=r.floors_low, floors_high=r.floors_high, cap_400_sqm=cap,
            frontages=(f.get("street_frontages") or {}).get("value"))
        out["policy_area"] = policy.as_dict() if policy else {"why": policy_why}

        units = d.get("units")
        if units:
            out["unit_mix"] = rights.unit_mix(units)
            out["balconies_sqm"], out["balconies_why"] = rights.balconies(out["unit_mix"]["units_max"])
            out["parking"] = rights.parking(out["unit_mix"]["units_max"], d.get("in_tama70"))
        if cap and d.get("registration_area"):
            alloc, why = rights.allocation(cap, d["registration_area"], total_is_ceiling=True)
            out["allocation_sqm"], out["allocation_why"] = alloc, why
        return out


def _scope_check(buildings):
    """מסלול מגרשים הוא 1–2 מבנים. שלושה ומעלה מנותבים למסלול מתחמים,
    שכללי הזכויות שלו אחרים לגמרי — זה ניתוב ולא פסילה."""
    if buildings is None:
        return rights.Check("scope_buildings", "מספר מבנים בחלקה", "unknown", rights.POLICY_URL, 2)
    status = "failed" if buildings < 1 else "passed" if buildings <= 2 else "routed"
    return rights.Check("scope_buildings", "מבנה אחד או שניים במסלול המגרשי", status,
                        rights.POLICY_URL, 2, f"{buildings} מבנים")


def _renewal(rs) -> dict[str, Any]:
    """הנימוקים רק כשיש חשד או אימות — אלה אינם נמסרים. בחלקה שנמסרת הם
    עשויים להחזיק הערת צוות, והתיק הולך ללקוח."""
    rs = rs if isinstance(rs, dict) else {}
    held = rs.get("status") in ("verified_renewed", "suspected")
    return {"status": rs.get("status"), "reasons": list(rs.get("reasons") or []) if held else []}


def _status(checks) -> str:
    if any(c.status == "failed" for c in checks):
        return "ineligible"
    if any(c.status == "routed" for c in checks):
        return "urban_renewal_compound"
    if all(c.status == "passed" for c in checks):
        return "eligible"
    return "needs_verification"
