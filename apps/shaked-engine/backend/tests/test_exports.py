"""ייצוא — ‏DOS-04, ובעיקר: שהגיליון מחשב אותו דבר כמו המחשבון.

‏`exports.py` מכיל עותק שני של שרשרת החישוב, בנוסחאות אקסל. שני עותקים
של אותו חשבון מתפצלים ברגע שאחד מהם מתוקן, והבדיקה כאן היא מה שמונע את
זה: היא מריצה את נוסחאות הגיליון בפייתון על אותם קלטים, ומשווה למחשבון.
"""
import re

import pytest

from app.cities.herzliya import exports
from app.services.economic.assumptions import get_assumptions
from app.services.economic.calculator import calculate_feasibility
from app.services.economic.schemas import FeasibilityInput

A = get_assumptions("herzliya")

DOSSIER = {
    "identity": {"address": "רחוב הבדיקה 1", "block": "6536", "parcel": "614",
                 "area_sqm": 952.0, "existing_units": 7},
    "rights": {
        "checks": [{"id": "permit_date", "label": "מועד היתר", "status": "passed",
                    "source_url": "https://example.test/p", "page": 3, "detail": "היתר 1978"},
                   {"id": "residential_share", "label": "70% למגורים", "status": "unknown",
                    "source_url": "https://example.test/p", "page": 3, "detail": None}],
        "status": "needs_verification",
        "floors": {"low": 8, "high": 9, "certain": False, "case_by_case": False},
        "cap_400_sqm": 3396.0, "cap_400_basis": "400% × 849 מ\"ר", "cap_400_certainty": "estimate",
        "notes": ["הערה 1"], "stale_fields": [],
    },
    "evidence": [{"field": "parcel_area", "value": 952.0, "certainty": "official", "decides": True,
                  "source_url": "https://example.test/g", "retrieved_at": "2026-09-12T00:00:00+00:00",
                  "location": "גוש 6536 חלקה 614", "method": "WFS"}],
    "economics": {},
    "gaps": {"unknown_gates": [{"id": "residential_share", "label": "70% למגורים", "detail": None}],
             "unobtainable": ["residential_share"], "checked_and_not_found": [],
             "never_asked": [], "stale_sources": [], "economic_inputs_missing": [],
             "note": "התיק אינו מוצג כארכיון מלא."},
    "versions": {"rules_version": "herzliya-policy-2026-02", "data_version": "2026-09-13",
                 "template_version": "dossier-1"},
    "delivery": {"delivered_at": "2026-09-13T10:00:00+00:00", "why_selected": None},
    "stale_fields": [],
}


def _with_economics():
    d = {**DOSSIER}
    d["economics"] = {
        "assumptions": A.report(), "assumptions_version": A.version,
        "assumptions_effective_date": A.effective_date.isoformat(),
        "inputs_missing": A.blocking(), "is_deliverable": False,
        "disclaimer": "אינה דוח שמאי חתום.",
        "scenario": calculate_feasibility(_inputs(), missing_inputs=A.blocking()).model_dump(),
    }
    return d


def _inputs():
    return FeasibilityInput(
        plot_area_sqm=952.0, existing_units=7, buildable_area_sqm=3396.0,
        sale_price_per_sqm=A.sale_price_per_sqm_ils.value,
        construction_cost_per_sqm=A.construction_cost_per_sqm_ils.value,
        soft_cost_ratio=A.soft_cost_ratio.value,
        demolition_cost_per_unit=A.demolition_cost_per_unit_ils.value,
        average_existing_unit_sqm=A.average_existing_unit_sqm.value,
        tenant_compensation_sqm_per_existing_unit=A.tenant_compensation_sqm_per_existing_unit.value,
        main_area_ratio=A.main_area_ratio.value, underground_ratio=A.underground_ratio.value,
        underground_cost_per_sqm=A.underground_cost_per_sqm_ils.value,
        tenant_rent_months=A.tenant_rent_months.value,
        tenant_monthly_rent_ils=A.tenant_monthly_rent_ils.value,
        tenant_moving_cost_ils=A.tenant_moving_cost_ils.value,
        tenant_legal_cost_per_unit_ils=A.tenant_legal_cost_per_unit_ils.value,
        marketing_ratio=A.marketing_ratio.value, guarantees_ratio=A.guarantees_ratio.value,
        finance_ratio=A.finance_ratio.value, betterment_levy_ratio=A.betterment_levy_ratio.value,
        vat_rate=A.vat_rate.value,
    )


# ── הבדיקה שמונעת משני העותקים להתפצל ──

def _evaluate_sheet(d):
    """מריץ את נוסחאות הגיליון בפייתון, לפי אותם מפתחות."""
    env = exports._scenario_inputs(d)
    for key, _, formula, _ in exports.OUTPUT_ROWS:
        expr = formula.lstrip("=")
        # הנוסחאות משתמשות במפתחות לוגיים; כאן הם משתני פייתון.
        expr = expr.replace("MIN(", "min(").replace("IF(", "_if(")
        expr = re.sub(r"\{(\w+)\}", r'env["\1"]', expr)
        env[key] = eval(expr, {"min": min, "_if": lambda c, a, b: a if c else b}, {"env": env})
    return env


def test_the_spreadsheet_computes_exactly_what_the_calculator_does():
    """שני עותקים של אותו חשבון מתפצלים ברגע שאחד מהם מתוקן. אם מישהו
    ישנה את `calculator.py` ולא את הנוסחאות, זו הבדיקה שתיפול."""
    d = _with_economics()
    sheet = _evaluate_sheet(d)
    calc = d["economics"]["scenario"]

    for sheet_key, calc_key in (("revenue", "total_revenue_ils"),
                                ("land", "land_cost_ils"),
                                ("build_cost", "total_construction_cost_ils"),
                                ("under", "total_underground_cost_ils"),
                                ("soft_cost", "total_soft_cost_ils"),
                                ("demo_cost", "total_demolition_cost_ils"),
                                ("tenant_cost", "total_tenant_cost_ils"),
                                ("marketing_cost", "total_marketing_ils"),
                                ("guarantee_cost", "total_guarantees_ils"),
                                ("finance_cost", "total_finance_ils"),
                                ("total_cost", "total_cost_ils"),
                                ("profit", "projected_profit_ils")):
        assert sheet[sheet_key] == pytest.approx(calc[calc_key], rel=1e-6), sheet_key
    assert sheet["margin"] == pytest.approx(calc["profit_margin_on_cost_ratio"], abs=5e-5)


def test_every_formula_references_a_cell_that_exists():
    """נוסחה שמפנה למפתח שאינו קיים נכתבת לקובץ ומתפוצצת רק באקסל."""
    known = set(exports.CELL) | {k for k, _, _, _ in exports.OUTPUT_ROWS}
    for key, _, formula, _ in exports.OUTPUT_ROWS:
        for ref in re.findall(r"\{(\w+)\}", formula):
            assert ref in known, f"{key} מפנה ל-{ref} שאינו קיים"


# ── הקבצים עצמם ──

def test_the_excel_is_a_real_workbook_with_both_sheets():
    import zipfile
    payload = exports.excel(_with_economics())
    assert payload[:2] == b"PK"
    names = zipfile.ZipFile(__import__("io").BytesIO(payload)).namelist()
    assert any("sheet1" in n for n in names) and any("sheet2" in n for n in names)


def test_the_scenario_sheet_holds_formulas_and_not_computed_numbers():
    """יזם שמקבל טבלת תוצאות יכול רק להאמין לנו."""
    import io, zipfile
    z = zipfile.ZipFile(io.BytesIO(exports.excel(_with_economics())))
    sheet = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "<f>" in sheet                       # יש נוסחאות
    assert sheet.count("<f>") >= len(exports.OUTPUT_ROWS)


def test_a_missing_input_is_an_empty_cell_and_not_a_zero():
    """‏DOS-03: *״אין להפוך נתון חסר לאפס״*. תא ריק מפוצץ את הנוסחה
    בגלוי; אפס נראה כמו מספר תקין ומייצר תשובה שגויה בשקט."""
    d = _with_economics()
    d["identity"] = {**d["identity"], "area_sqm": None}
    values = exports._scenario_inputs(d)
    assert values["plot"] is None
    assert exports.excel(d)[:2] == b"PK"        # ועדיין נכתב


def test_the_pdf_is_a_real_pdf():
    payload = exports.pdf(_with_economics())
    assert payload[:5] == b"%PDF-"
    assert len(payload) > 3000


def test_a_font_without_hebrew_is_refused_rather_than_drawing_boxes():
    """‏reportlab מגיע עם Vera בלבד ואין בו עברית — הטקסט היה מצויר
    כריבועים **בלי שגיאה**, וזה הסוג הגרוע של כישלון."""
    import os
    original = exports.FONT_CANDIDATES[:]
    exports.FONT_CANDIDATES[:] = ["/nonexistent/font.ttf"]
    try:
        with pytest.raises(RuntimeError, match="גופן"):
            exports._font_path()
    finally:
        exports.FONT_CANDIDATES[:] = original
    assert any(os.path.exists(p) for p in exports.FONT_CANDIDATES)
