"""‏W8 · מחשבון התרחיש בתוך הדוח הכלכלי (בקשות 12 ו-14 של השותפים).

הנתונים שלנו הם ברירת המחדל, והיזם משנה אותם. הבדיקות כאן על שלושה דברים
שנכשלים בשקט:

- **ברירת המחדל זזה.** תרחיש בלי שינויים חייב להיות התיק עצמו, מספר במספר.
- **שינוי שלא מגיע לכל מקום.** מחיר שנכנס לרווח ולא לטבלת ההנחות, השבחה
  שנכנסת לטבלה ולא לרווח, תמהיל שמוצג ואינו משנה את ההכנסות — ״דוח 0 נגזר
  מהבחירה״ רק כשכל אלה זזים יחד, גם באקסל.
- **דליפה.** תמהיל שנשמר על ההזדמנות הופיע בתיק של חברה אחרת.
"""
import uuid

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from app.cities.herzliya import exports
from app.cities.herzliya.dossier import build, scenario_for
from app.cities.herzliya.rules import HerzliyaCityRules
from app.cities.herzliya.scenario import DEVELOPER, ScenarioOverrides, ScenarioRejected
from app.cities.herzliya.surfaces import _cells, _words, compare
from app.core.database import get_async_session
from app.core.security import current_active_user, current_superuser
from app.main import app
from app.services.unit_mix.service import DEFAULT_UNIT_AREAS_SQM
from tests.test_dossier import _company, _delivered, _small, _with_resolved_inputs
from tests.test_exports import _evaluate_sheet

RULES = HerzliyaCityRules()


async def _scenario(session, opp, **overrides):
    return await scenario_for(session, RULES, opp, ScenarioOverrides(**overrides))


async def _default(session, opp, company):
    return (await build(session, RULES, opp.id, company.id))["economics"]


# ── ברירת המחדל אינה זזה ──

@pytest.mark.asyncio
async def test_a_scenario_without_changes_is_the_dossier_itself(session):
    c, opp = await _with_resolved_inputs(session, "9801")
    opp.existing_units = 10
    await session.flush()
    default = await _default(session, opp, c)
    assert "overrides_applied" not in default

    empty = await _scenario(session, opp)
    assert empty.pop("overrides_applied") == []
    assert empty == default

    # ערכים שזהים לברירת המחדל אינם ״הוזן על ידי היזם״
    rows = default["assumptions"]
    same = await _scenario(session, opp,
                           sale_price_per_sqm=rows["sale_price_per_sqm_ils"]["value"],
                           developer_profit_target_ratio=rows["developer_profit_target_ratio"]["value"],
                           area_basis="policy_base")
    assert same.pop("overrides_applied") == []
    assert same == default


# ── מחיר, שטח, השבחה ויעד רווח ──

@pytest.mark.asyncio
async def test_a_sale_price_override_moves_the_profit_and_marks_the_row(session):
    c, _, opp = await _delivered(session, block="9802")
    default = await _default(session, opp, c)
    price = default["assumptions"]["sale_price_per_sqm_ils"]["value"]

    econ = await _scenario(session, opp, sale_price_per_sqm=price + 8_000)
    row = econ["assumptions"]["sale_price_per_sqm_ils"]
    assert row["value"] == price + 8_000
    assert row["status"] == DEVELOPER and row["source"] == "הוזן על ידי היזם"
    assert row["default"] == price
    assert econ["scenario"]["projected_profit_ils"] > default["scenario"]["projected_profit_ils"]
    assert econ["overrides_applied"] == [{
        "id": "sale_price_per_sqm", "label": row["label"], "default": price, "value": price + 8_000,
        "unit": "ILS/sqm", "unit_label": "₪ למ״ר"}]
    # שורות העלות והסייגים נגזרים מהמחיר של היזם, לא מהאומדן שלנו
    revenue = next(r for r in econ["cost_rows"] if r["id"] == "revenue")
    assert f"{price + 8_000:,.0f} ₪" in revenue["formula"] and "הוזן על ידי היזם" in revenue["source"]
    assert "sale_price_per_sqm_ils_unresolved" not in {x["id"] for x in econ["caveats"]}
    assert sum(r["value_ils"] for r in econ["cost_rows"]) == pytest.approx(
        econ["scenario"]["projected_profit_ils"], abs=2)
    # ושום דבר לא נשמר: התיק עצמו לא זז
    assert (await _default(session, opp, c)) == default


@pytest.mark.asyncio
async def test_the_400_percent_basis_is_the_cap_scenario_of_the_comparison(session):
    c, opp = await _small(session, "9803", street_frontages=1)
    default = await _default(session, opp, c)
    assert default["area_basis"] == "policy"

    econ = await _scenario(session, opp, area_basis="cap_400")
    card = econ["scenarios"]["cap_400"]
    assert econ["area_basis"] == "cap_400"
    assert econ["buildable_area_sqm"] == pytest.approx(card["area_sqm"])
    assert econ["before_levy"]["profit_ils"] == pytest.approx(card["profit_before_levy_ils"])
    assert econ["scenario"]["developer_allocation_sqm"] == pytest.approx(card["developer_allocation_sqm"])
    assert econ["scenarios"] == default["scenarios"]            # ההשוואה עצמה לא זזה
    assert econ["overrides_applied"][0]["id"] == "area_basis"
    assert econ["overrides_applied"][0]["default"] == pytest.approx(default["buildable_area_sqm"])
    # הסייג אומר על איזה שטח הרווח מחושב
    caveat = next(x["text"] for x in econ["caveats"] if x["id"] == "area_basis_developer")
    assert "תקרת ה-400%" in caveat and "policy_area_below_cap" not in {x["id"] for x in econ["caveats"]}


@pytest.mark.asyncio
async def test_an_area_the_law_does_not_allow_is_refused(session):
    c, opp = await _small(session, "9804", street_frontages=1)
    cap = (await _default(session, opp, c))["scenarios"]["cap_400"]["area_sqm"]
    with pytest.raises(ScenarioRejected, match="תקרת ה-400%"):
        await _scenario(session, opp, area_basis="custom", custom_area_sqm=cap + 100)
    econ = await _scenario(session, opp, area_basis="custom", custom_area_sqm=cap * 0.6)
    assert econ["buildable_area_sqm"] == pytest.approx(cap * 0.6)
    assert econ["buildable_certainty"] == DEVELOPER


@pytest.mark.asyncio
async def test_a_betterment_the_developer_enters_replaces_the_estimate_after_levy(session):
    c, opp = await _with_resolved_inputs(session, "9805")
    opp.existing_units = 10
    await session.flush()
    default = await _default(session, opp, c)
    estimate = default["after_levy"]["betterment_ils"]
    assert estimate > 0, "הבדיקה צריכה אומדן להחליף"

    econ = await _scenario(session, opp, betterment_ils=1_000_000)
    after, levy = econ["after_levy"], econ["betterment"]["levy"]
    assert after["betterment_ils"] == 1_000_000 and after["levy_ils"] == pytest.approx(250_000)
    assert after["margin_low"] == after["margin"] == after["margin_high"]      # מספר של היזם, בלי טווח
    assert levy["estimate_ils"] == levy["low_ils"] == levy["high_ils"] == pytest.approx(250_000)
    assert econ["scenario"]["betterment_levy_ils"] == pytest.approx(250_000)
    assert econ["scenario"]["projected_profit_ils"] == pytest.approx(after["profit_ils"])
    # הרווח הוא בדיוק הרווח עם ההשבחה הזו, ולא עם האומדן
    assert econ["before_levy"] == default["before_levy"]
    assert after["profit_ils"] > default["after_levy"]["profit_ils"]

    row = econ["assumptions"]["betterment_base_ils"]
    assert row["value"] == 1_000_000 and row["status"] == DEVELOPER
    assert row["default"] == pytest.approx(estimate)
    assert econ["profit_verdict"].endswith("אחרי היטל לפי ההשבחה שהזין היזם")
    assert "שהזין היזם" in econ["betterment"]["summary"]
    assert econ["betterment"]["explain"][1]["title"] == "ההשבחה שהזין היזם"
    assert next(r for r in econ["cost_rows"] if r["id"] == "levy")["value_ils"] == pytest.approx(-250_000)

    # האקסל מחשב אותו רווח, מאותו תא השבחה
    d = await build(session, RULES, opp.id, c.id, ScenarioOverrides(betterment_ils=1_000_000))
    sheet = _evaluate_sheet(d)
    assert sheet["levy_base"] == 1_000_000
    assert sheet["profit"] == pytest.approx(after["profit_ils"], abs=5)


@pytest.mark.asyncio
async def test_a_20_percent_target_changes_the_verdict(session):
    c, _, opp = await _delivered(session, block="9806")
    opp.existing_units = 16                               # כ-19% על העלות
    await session.flush()
    default = await _default(session, opp, c)
    assert default["scenario"]["meets_developer_target"]
    assert default["profit_verdict"].startswith("מעל הרווח היזמי המזערי (16%)")

    econ = await _scenario(session, opp, developer_profit_target_ratio=0.20)
    assert econ["scenario"]["profit_margin_on_cost_ratio"] == pytest.approx(
        default["scenario"]["profit_margin_on_cost_ratio"])           # הרווח עצמו לא זז
    assert not econ["scenario"]["meets_developer_target"]
    assert econ["before_levy"]["meets_target"] is False
    assert econ["profit_verdict"].startswith("מתחת לרווח היזמי המזערי (20%)")
    assert econ["betterment"]["profit_target_ratio"] == 0.20
    assert econ["betterment"]["category"] == "no_threshold"
    assert econ["rights_verdict"]["case"] != "A"


# ── תמהיל ──

async def _mixable(session, block):
    """‏20 דירות על מגרש גדול: יש תמהיל חוקי (28 דירות מחייבות 51 דירות ליזם)."""
    c, _, opp = await _delivered(session, block=block)
    opp.existing_units = 20
    await session.flush()
    return c, opp


@pytest.mark.asyncio
async def test_an_optimized_mix_derives_the_revenue_and_reads_the_same_on_every_surface(session):
    c, opp = await _mixable(session, "9807")
    default = await _default(session, opp, c)
    econ = await _scenario(session, opp, mix="optimize")
    mix, s = econ["unit_mix"], econ["scenario"]

    assert mix["rows"] and mix["source"] == "optimize"
    assert all(r["area_sqm"] == DEFAULT_UNIT_AREAS_SQM[r["rooms"]] for r in mix["rows"])
    used = sum(r["units"] * r["area_sqm"] for r in mix["rows"])
    assert used == pytest.approx(mix["developer_used_sqm"]) and used <= mix["developer_available_sqm"]
    assert mix["developer_units"] == sum(r["units"] for r in mix["rows"])
    # ההכנסות של היזם הן הדירות שבתמהיל, במחיר התרחיש, נטו ממע״מ
    price = econ["assumptions"]["sale_price_per_sqm_ils"]["value"]
    assert mix["developer_sale_revenue_ils"] == pytest.approx(used * price)
    assert s["developer_revenue_ils"] == pytest.approx(used * price / 1.18, abs=1)
    assert s["developer_revenue_ils"] != default["scenario"]["developer_revenue_ils"]
    assert mix["summary"].startswith("תמהיל מיטבי ליזם (אומדן):")
    assert "הרווח מחושב לפי הדירות שבתמהיל" in mix["summary"]
    assert econ["overrides_applied"][-1]["id"] == "mix"
    assert "בלי התמהיל" in econ["rights_verdict"]["text"]
    assert "תמהיל" in next(r for r in econ["cost_rows"] if r["id"] == "revenue")["formula"]

    # האקסל מחשב את אותו רווח מתא הכנסות התמהיל, וה-PDF מדפיס את אותו משפט
    d = await build(session, RULES, opp.id, c.id, ScenarioOverrides(mix="optimize"))
    xlsx, pdf = exports.excel(d), exports.pdf(d)
    assert compare(d, xlsx, pdf) == []
    assert _evaluate_sheet(d)["mix_revenue"] == pytest.approx(mix["developer_sale_revenue_ils"])
    strings = {v for kind, v in _cells(xlsx).values() if kind == "s"}
    assert mix["summary"] in strings
    words = set().union(*(_words(ln) for page in pymupdf.open(stream=pdf, filetype="pdf")
                          for ln in page.get_text().splitlines()))
    assert {"תמהיל", "ליזם", "חד׳"} <= words, "שורת התמהיל אינה ב-PDF"


@pytest.mark.asyncio
async def test_a_typed_mix_is_priced_and_a_mix_that_does_not_fit_is_refused(session):
    c, opp = await _mixable(session, "9808")
    econ = await _scenario(session, opp, mix=[{"rooms": 3, "units": 30}, {"rooms": 4, "units": 10}])
    mix = econ["unit_mix"]
    assert mix["source"] == DEVELOPER
    assert [(r["rooms"], r["units"]) for r in mix["rows"]] == [(3, 30), (4, 10)]
    assert mix["developer_sale_revenue_ils"] == pytest.approx(
        (30 * 75 + 10 * 100) * econ["assumptions"]["sale_price_per_sqm_ils"]["value"])
    assert mix["summary"].startswith("תמהיל שהזין היזם:")
    # ‏40 דירות ליזם ו-20 לבעלים הן 60 — בתוך מכפיל הדירות, ולכן בלי אזהרה
    assert mix["policy_warnings"] == []

    few = await _scenario(session, opp, mix=[{"rooms": 5, "units": 4}])
    assert any("מכפיל הדירות" in w for w in few["unit_mix"]["policy_warnings"])   # מוזהר, לא נדחה
    with pytest.raises(ScenarioRejected, match="אינו נכנס בשטח ליזם"):
        await _scenario(session, opp, mix=[{"rooms": 5, "units": 400}])


# ── הדליפה: תמהיל שנשמר על ההזדמנות ──

@pytest.mark.asyncio
async def test_a_mix_saved_on_the_opportunity_never_reaches_a_dossier(session):
    """‏B15 שמר תמהיל ב-`metadata_json`, וההזדמנות משותפת לכל החברות שקיבלו אותה."""
    from app.services.unit_mix.service import prepare_unit_mix

    c, opp = await _mixable(session, "9809")
    before = await _default(session, opp, c)
    rights_ = (await build(session, RULES, opp.id, c.id))["rights"]
    opp.metadata_json = {**(opp.metadata_json or {}), "assessment": {
        "cap_400_sqm": rights_["cap_400_sqm"],
        "policy_area_sqm": rights_["policy_area"]["base"]["sqm"],
        "floors_low": (rights_.get("floors") or {}).get("low")}}
    await session.flush()
    prepared = await prepare_unit_mix(session, opp, compensation_sqm_per_existing_unit=30, persist=True)
    assert opp.metadata_json["planned_unit_mix"] == prepared.planned_unit_mix

    after = await _default(session, opp, c)
    assert after["unit_mix"] == {"rows": [], "summary": None}
    assert after["scenario"] == before["scenario"]


# ── ה-API ──

async def _user(session, company, superuser=False):
    from app.models.tenant import User
    u = User(email=f"{uuid.uuid4().hex[:8]}@s.local", hashed_password="x", is_active=True,
             is_superuser=superuser, is_verified=True, full_name="יזם", role="member",
             company_id=company.id)
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
async def api(session):
    """לקוח HTTP על טרנזקציית הבדיקה. ‏`api.as_user(u)` מחליף את המשתמש."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        def as_user(u):
            app.dependency_overrides[get_async_session] = lambda: session
            app.dependency_overrides[current_active_user] = lambda: u
            app.dependency_overrides[current_superuser] = lambda: u
        client.as_user = as_user
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_the_scenario_endpoint_is_only_for_the_company_that_got_the_dossier(session, api):
    c, u, opp = await _delivered(session, block="9810")
    url = f"/api/v1/candidates/herzliya/{opp.id}/dossier/scenario"
    api.as_user(u)
    r = await api.post(url, json={"sale_price_per_sqm": 50_000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overrides_applied"][0]["id"] == "sale_price_per_sqm"
    assert body["economics"]["assumptions"]["sale_price_per_sqm_ils"]["value"] == 50_000

    other, _ = await _company(session, "חברה אחרת")
    api.as_user(await _user(session, other))
    assert (await api.post(url, json={"sale_price_per_sqm": 50_000})).status_code == 404
    assert (await api.post(f"/api/v1/candidates/herzliya/{opp.id}/dossier.xlsx",
                           json={"sale_price_per_sqm": 50_000})).status_code == 404
    assert (await api.post(f"/api/v1/candidates/herzliya/{uuid.uuid4()}/dossier/scenario",
                           json={})).status_code == 404


@pytest.mark.asyncio
async def test_a_mix_that_does_not_fit_is_a_422_with_a_sentence(session, api):
    c, u, opp = await _delivered(session, block="9811")
    api.as_user(u)
    r = await api.post(f"/api/v1/candidates/herzliya/{opp.id}/dossier/scenario",
                       json={"mix": [{"rooms": 5, "units": 400}]})
    assert r.status_code == 422
    assert "אינו נכנס בשטח ליזם" in r.json()["detail"]
    # קלט מחוץ לטווח נדחה, ולא מתפרש כברירת מחדל
    assert (await api.post(f"/api/v1/candidates/herzliya/{opp.id}/dossier/scenario",
                           json={"sale_price_per_sqm": 42})).status_code == 422
    assert (await api.post(f"/api/v1/candidates/herzliya/{opp.id}/dossier/scenario",
                           json={"unknown_field": 1})).status_code == 422


@pytest.mark.asyncio
async def test_a_scenario_export_carries_the_developer_values_into_the_spreadsheet(session, api):
    c, opp = await _small(session, "9812", street_frontages=1)
    api.as_user(await _user(session, c))
    body = {"area_basis": "custom", "custom_area_sqm": 3_000, "sale_price_per_sqm": 51_000}

    r = await api.post(f"/api/v1/candidates/herzliya/{opp.id}/dossier.xlsx", json=body)
    assert r.status_code == 200, r.text
    assert "-scenario.xlsx" in r.headers["content-disposition"]
    cells = _cells(r.content)
    assert cells[exports.CELL["buildable"]] == ("n", 3_000)
    assert cells[exports.CELL["price"]] == ("n", 51_000)
    strings = {v for kind, v in cells.values() if kind == "s"}
    assert any(s_.startswith(exports.SCENARIO_TITLE) for s_ in strings)
    assert "הוזן על ידי היזם" in strings

    pdf = await api.post(f"/api/v1/candidates/herzliya/{opp.id}/dossier.pdf", json=body)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    lines = [_words(ln) for page in pymupdf.open(stream=pdf.content, filetype="pdf")
             for ln in page.get_text().splitlines()]
    assert any({"תרחיש", "מותאם", "שהיזם", "שינה"} <= w for w in lines)
    assert any({"מחיר", "מכירה", "המחדל"} <= w for w in lines)

    # ה-GET לא השתנה: אותו קובץ כמו תמיד, בלי כותרת תרחיש
    plain = await api.get(f"/api/v1/candidates/herzliya/{opp.id}/dossier.xlsx")
    assert plain.status_code == 200 and "-scenario" not in plain.headers["content-disposition"]
    plain_strings = {v for kind, v in _cells(plain.content).values() if kind == "s"}
    assert not any(s_.startswith(exports.SCENARIO_TITLE) for s_ in plain_strings)
    assert _cells(plain.content)[exports.CELL["price"]] != ("n", 51_000)


@pytest.mark.asyncio
async def test_saving_a_mix_on_the_shared_opportunity_is_refused_to_customers(session, api):
    c, opp = await _mixable(session, "9813")
    rights_ = (await build(session, RULES, opp.id, c.id))["rights"]
    opp.metadata_json = {**(opp.metadata_json or {}), "assessment": {
        "cap_400_sqm": rights_["cap_400_sqm"],
        "policy_area_sqm": rights_["policy_area"]["base"]["sqm"]}}
    await session.flush()
    api.as_user(await _user(session, c))
    url = f"/api/v1/unit-mix/{opp.id}/optimize"

    refused = await api.post(url, json={"persist": True})
    assert refused.status_code == 403 and "לצוות" in refused.json()["detail"]
    # גם למזהה שאינו קיים — הסירוב אינו אומר דבר על ההזדמנות
    assert (await api.post(f"/api/v1/unit-mix/{uuid.uuid4()}/optimize",
                           json={"persist": True})).status_code == 403

    ok = await api.post(url, json={})
    assert ok.status_code == 200, ok.text
    assert ok.json()["planned_unit_mix"]
    assert "planned_unit_mix" not in opp.metadata_json                  # ברירת המחדל: לא נשמר

    api.as_user(await _user(session, c, superuser=True))
    assert (await api.post(url, json={"persist": True})).status_code == 200
