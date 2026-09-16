"""ייצוא התיק — ‏DOS-04: *״ייצוא PDF של התיק ו-Excel של נתוני התרחיש
נכללים בגרסה הראשונה״*.

**גיליון התרחיש נכתב עם נוסחאות חיות ולא עם מספרים מחושבים.** זו ההחלטה
המרכזית כאן, והיא נובעת מ-ACC-09: *״חישוב תרחיש נבדק מול מקרי ייחוס...
וניתן לשחזור לפי ההנחות שנשמרו״*. יזם שמקבל טבלה של תוצאות יכול רק
להאמין לנו; יזם שמקבל נוסחאות יכול לשנות מחיר מכירה ולראות את המרווח זז,
ולבדוק את החשבון שלנו שורה-שורה.

הנוסחאות משקפות את `calculator.py` אחת לאחת. כשהאחד משתנה, השני חייב —
ויש בדיקה שמשווה ביניהם על אותו קלט.
"""
import io
from typing import Any

# ── PDF בעברית ──
#
# נדרשת גופן שיש בו אותיות עבריות. ‏reportlab מגיע עם Vera בלבד, ואין בו
# עברית — טקסט היה מוצג כריבועים בלי שגיאה. הרשימה עוברת על המקומות
# המקובלים בשלוש מערכות הפעלה, ואם אין — נזרקת שגיאה מפורשת ולא PDF פגום.
FONT_CANDIDATES = [
    "/Library/Fonts/Arial Unicode.ttf",                              # macOS
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",               # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",                        # Fedora
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:/Windows/Fonts/arial.ttf",                                    # Windows
]

PAGE_W, PAGE_H = 595, 842          # A4 בנקודות
MARGIN_R, MARGIN_L = 545, 50


def _font_path() -> str:
    import os
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError(
        "לא נמצא גופן עם אותיות עבריות. יש להתקין DejaVu Sans "
        "(‏apt install fonts-dejavu-core) או להוסיף נתיב ל-FONT_CANDIDATES."
    )


def _rtl(text: str) -> str:
    """טקסט לוגי → סדר תצוגה. ‏reportlab מצייר משמאל לימין בלבד."""
    from bidi.algorithm import get_display
    return get_display(str(text))


def _v(x: Any, unit: str = "") -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "כן" if x else "לא"
    if isinstance(x, (int, float)):
        return f"{x:,.0f}{unit}" if abs(x) >= 100 else f"{x:,.2f}{unit}".rstrip("0").rstrip(".") + unit[:0]
    return str(x)


def pdf(d: dict[str, Any]) -> bytes:
    """התיק כמסמך. ‏RTL אמיתי, לא טקסט אנגלי בעברית."""
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    if "Shaked" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Shaked", _font_path()))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"תיק · {d['identity']['address']}")
    y = [PAGE_H - 60]

    def header():
        c.setFont("Shaked", 9)
        c.setFillColorRGB(0.42, 0.40, 0.36)
        c.drawRightString(MARGIN_R, PAGE_H - 40, _rtl("שקדן · תיק הזדמנות — חלופת שקד"))
        c.setStrokeColorRGB(0.88, 0.88, 0.86)
        c.line(MARGIN_L, PAGE_H - 48, MARGIN_R, PAGE_H - 48)
        y[0] = PAGE_H - 70

    def line(text, size=9.5, colour=(0.10, 0.10, 0.10), gap=4, indent=0):
        for chunk in simpleSplit(str(text), "Shaked", size, MARGIN_R - MARGIN_L - indent):
            if y[0] < 60:
                c.showPage()
                header()
            c.setFont("Shaked", size)
            c.setFillColorRGB(*colour)
            c.drawRightString(MARGIN_R - indent, y[0], _rtl(chunk))
            y[0] -= size + gap

    def rule():
        y[0] -= 4
        c.setStrokeColorRGB(0.88, 0.88, 0.86)
        c.line(MARGIN_L, y[0], MARGIN_R, y[0])
        y[0] -= 12

    header()
    ident = d["identity"]
    line(ident["address"], 17, (0.06, 0.15, 0.12), gap=3)
    line(f'גוש {ident["block"]} · חלקה {ident["parcel"]}'
         + (f' · {ident["area_sqm"]:,.0f} מ"ר' if ident.get("area_sqm") else "")
         + (f' · {ident["existing_units"]} דירות קיימות' if ident.get("existing_units") else ""),
         9.5, (0.42, 0.40, 0.36))
    rule()

    # ── שרשרת הזכויות ──
    STATUS = {"passed": "עבר", "failed": "נכשל", "unknown": "לא ידוע",
              "routed": "נותב למתחמים", "undefined": "המדיניות שותקת",
              "needs_measurement": "דורש מדידה"}
    line("שרשרת הזכויות", 13, (0.06, 0.15, 0.12), gap=6)
    for g in d["rights"]["checks"]:
        page = f" · עמ׳ {g['page']}" if g.get("page") else ""
        line(f'[{STATUS.get(g["status"], g["status"])}]  {g["label"]}{page}', 9.5, gap=2)
        if g.get("detail"):
            line(g["detail"], 8.5, (0.42, 0.40, 0.36), gap=5, indent=14)

    f = d["rights"]["floors"]
    floors = "—" if f["low"] is None else (
        f'{f["low"]:g}–{f["high"]:g}' if f["high"] not in (None, f["low"]) else f'{f["low"]:g}')
    rule()
    line(f'קומות מותרות: {floors}'
         + ("  ·  דורש מדידה" if not f["certain"] and f["low"] is not None else "")
         + (f'   |   תקרת 400%: {d["rights"]["cap_400_sqm"]:,.0f} מ"ר'
            if d["rights"].get("cap_400_sqm") else ""), 11, (0.06, 0.15, 0.12))
    if d["rights"].get("cap_400_basis"):
        line(d["rights"]["cap_400_basis"], 8.5, (0.42, 0.40, 0.36))
    rule()

    # ── ראיות ──
    line("מאיפה הגיע כל מספר", 13, (0.06, 0.15, 0.12), gap=6)
    for r in d["evidence"]:
        decides = "מכריע" if r["decides"] else "אינו מכריע"
        name = r.get("label") or r["field"]
        cert = r.get("certainty_label") or r["certainty"]
        line(f'{name}: {_v(r["value"])}  ·  {cert}  ·  {decides}', 9, gap=1)
        line(f'{r.get("location") or ""}  ·  נשלף {(r.get("retrieved_at") or "")[:10]}',
             7.5, (0.55, 0.53, 0.49), gap=4, indent=14)
    rule()

    # ── תרחיש ──
    econ = d["economics"]
    line("תרחיש כלכלי", 13, (0.06, 0.15, 0.12), gap=3)
    line(econ["disclaimer"], 8.5, (0.42, 0.40, 0.36), gap=6)
    s = econ.get("scenario")
    if s:
        for name, key in (("הכנסות (נטו ממע״מ)", "total_revenue_ils"),
                          ("קרקע — פיצוי הדיירים", "land_cost_ils"),
                          ("בנייה מעל הקרקע", "total_construction_cost_ils"),
                          ("חניון תת-קרקעי", "total_underground_cost_ils"),
                          ("עלויות רכות", "total_soft_cost_ils"),
                          ("הריסה", "total_demolition_cost_ils"),
                          ("שכירות והובלות לדיירים", "total_tenant_cost_ils"),
                          ("שיווק ותיווך", "total_marketing_ils"),
                          ("ערבויות וביטוח", "total_guarantees_ils"),
                          ("מימון", "total_finance_ils"),
                          ("היטל השבחה", "betterment_levy_ils")):
            if key == "betterment_levy_ils" and _levy_unknown(econ):
                # ‏B13 · ״היטל השבחה: 0 ₪״ נקרא כמו ״אין היטל״. הבסיס דורש
                # שומה, ולכן מודפס המשפט שהשרת כתב — התקרה, לא אפס.
                line(econ["betterment"]["summary"], 9, (0.54, 0.38, 0.00), gap=2)
                continue
            line(f'{name}: {s[key]:,.0f} ₪', 9, gap=2)
            if key == "betterment_levy_ils" and (econ.get("betterment") or {}).get("summary"):
                # ‏W2 · האומדן בתוך הרווח, והמשפט אומר שזה אומדן ומה התקרה.
                line(econ["betterment"]["summary"], 8.5, (0.54, 0.38, 0.00), gap=2, indent=10)
        line(f'רווח: {s["projected_profit_ils"]:,.0f} ₪  ·  '
             f'{s["profit_margin_on_cost_ratio"]:.0%} על העלות', 11, (0.06, 0.15, 0.12), gap=5)
        if econ.get("profit_verdict"):
            line(econ["profit_verdict"], 9, (0.54, 0.38, 0.00) if not s.get("meets_developer_target")
                 else (0.12, 0.37, 0.33), gap=4)
        # ‏W2 · הזכויות לפי המדיניות מול 400%, ומה נדרש כדי להיות כלכלי.
        _pdf_rights_comparison(econ, d["rights"], line)
        # ‏B8 · הסייגים נוסעים עם הרווח. פרק הזכויות כתב ״התקרה מנופחת״,
        # והתרחיש מתחתיו הציג רווח בלי מילה.
        if econ.get("caveats"):
            line("על מה הרווח נשען:", 9, (0.54, 0.38, 0.00), gap=2)
            for cav in econ["caveats"]:
                line(f'· {cav["text"]}', 8.5, (0.42, 0.40, 0.36), gap=2, indent=10)
            y[0] -= 3
        # ‏B15 · התמהיל שהיזם חישב. מוצג ואינו משנה את הרווח שמעליו.
        if (econ.get("unit_mix") or {}).get("summary"):
            line(econ["unit_mix"]["summary"], 8.5, (0.06, 0.15, 0.12), gap=4)
    else:
        line(econ.get("why", "לא חושב תרחיש."), 9.5, (0.54, 0.20, 0.12))
    if not econ["is_deliverable"]:
        # נופל למשפט הקצר ולא נעלם: סייג שנעלם קורא כמו תרחיש שנמסר.
        line(econ.get("not_delivered_reason") or "התרחיש אינו נמסר כתוצאה.",
             9, (0.54, 0.38, 0.00))
    rule()

    # ── פערים ──
    line("פערים", 13, (0.06, 0.15, 0.12), gap=3)
    line(d["gaps"]["note"], 8.5, (0.42, 0.40, 0.36), gap=6)
    for title, key in (("שערים שלא נענו", "unknown_gates"),
                       ("אין להם מקור פתוח", "unobtainable"),
                       ("נבדק ולא נמצא", "checked_and_not_found"),
                       ("מעולם לא נשאל", "never_asked"),
                       ("מקורות שהתיישנו", "stale_sources")):
        items = d["gaps"][key]
        names = [i["label"] if isinstance(i, dict) else str(i) for i in items]
        line(f'{title}: {", ".join(names) if names else "אין"}', 9, gap=3)

    v = d["versions"]
    y[0] -= 6
    line(f'כללים {v["rules_version"]} · נתונים {v["data_version"] or "—"} · '
         f'תבנית {v["template_version"]}', 8, (0.55, 0.53, 0.49))

    c.showPage()
    c.save()
    return buf.getvalue()


# ───────────────────────── Excel ─────────────────────────
#
# הקלטים והנוסחאות מסודרים כך ששורה בגיליון מקבילה לשורה במחשבון. ‏`ref`
# הוא תא הקלט, ו-`formula` בנוי עליו — אם מישהו יזיז שורה כאן ולא שם,
# הבדיקה שמשווה בין השניים תיפול.

INPUT_ROWS = [
    ("plot", 'שטח המגרש', "מ״ר"),
    ("units", "דירות קיימות", "יח״ד"),
    ("buildable", 'תקרת 400% — שטח בנוי מעל הקרקע', "מ״ר"),
    ("main_ratio", "שיעור השטח העיקרי", "יחס"),
    ("under_ratio", "שיעור חניון תת-קרקעי", "יחס"),
    ("price", 'מחיר מכירה למ״ר (כולל מע״מ)', "₪"),
    ("vat", "מע״מ", "יחס"),
    ("build", 'עלות בנייה למ״ר', "₪"),
    ("under_cost", 'עלות חניון למ״ר', "₪"),
    ("soft", "עלויות רכות", "יחס מעלות הבנייה"),
    ("demo", "הריסה ליח״ד", "₪"),
    ("avg_unit", "שטח דירה קיימת ממוצע", "מ״ר"),
    ("comp", "תוספת לדייר", "מ״ר"),
    ("rent_months", "חודשי שכירות לדיירים", "חודשים"),
    ("rent", "שכ״ד חודשי לדייר", "₪"),
    ("moving", "הובלות לדייר", "₪"),
    ("legal", "עו״ד ושמאי לדייר", "₪"),
    ("marketing", "שיווק ותיווך", "יחס מההכנסות"),
    ("guarantees", "ערבויות וביטוח", "יחס מההכנסות"),
    ("finance", "מימון", "יחס מהעלויות"),
    ("levy_rate", "היטל השבחה — שיעור", "יחס מההשבחה"),
    ("levy_base", "ההשבחה (שומה)", "₪"),
]

FIRST_INPUT_ROW = 2                       # אחרי הכותרת
CELL = {key: f"B{FIRST_INPUT_ROW + i + 1}" for i, (key, _, _) in enumerate(INPUT_ROWS)}

OUTPUT_ROWS = [
    ("sellable", "שטח נמכר (עיקרי)", "={buildable}*{main_ratio}", "מ״ר"),
    ("tenant_area", "שטח לדיירים", "=MIN({units}*({avg_unit}+{comp}),{sellable})", "מ״ר"),
    ("dev_area", "שטח ליזם", "={sellable}-{tenant_area}", "מ״ר"),
    ("net_price", 'מחיר נטו למ״ר', "={price}/(1+{vat})", "₪"),
    ("revenue", "הכנסות (נטו ממע״מ)", "={sellable}*{net_price}", "₪"),
    ("dev_revenue", "מתוכן: דירות היזם", "={dev_area}*{net_price}", "₪"),
    ("land", "קרקע — פיצוי הדיירים", "={tenant_area}*{net_price}", "₪"),
    ("build_cost", "בנייה מעל הקרקע", "={buildable}*{build}", "₪"),
    ("under", "חניון תת-קרקעי", "={buildable}*{under_ratio}*{under_cost}", "₪"),
    ("soft_cost", "עלויות רכות", "=({build_cost}+{under})*{soft}", "₪"),
    ("demo_cost", "הריסה", "={units}*{demo}", "₪"),
    ("tenant_cost", "שכירות, הובלות ויועצים לדיירים",
     "={units}*({rent_months}*{rent}+{moving}+{legal})", "₪"),
    # ‏E1 · שיווק על הדירות שהיזם מוכר, ומימון בלי שווי דירות הבעלים.
    ("marketing_cost", "שיווק ותיווך", "={dev_revenue}*{marketing}", "₪"),
    ("guarantee_cost", "ערבויות וביטוח", "={revenue}*{guarantees}", "₪"),
    ("levy_cost", "היטל השבחה", "={levy_base}*{levy_rate}", "₪"),
    ("before_finance", "סך עלויות לפני מימון",
     "={land}+{build_cost}+{under}+{soft_cost}+{demo_cost}+{tenant_cost}"
     "+{marketing_cost}+{guarantee_cost}+{levy_cost}", "₪"),
    ("finance_cost", "מימון", "=({before_finance}-{land})*{finance}", "₪"),
    ("total_cost", "סך העלויות", "={before_finance}+{finance_cost}", "₪"),
    ("profit", "רווח", "={revenue}-{total_cost}", "₪"),
    ("margin", "רווח על העלות", '=IF({total_cost}>0,{profit}/{total_cost},"")', "%"),
]


# תא קלט ← שורה בטבלת ההנחות. מקור אחד לערך, לסטטוס ולמקור שלו.
INPUT_ASSUMPTION = {
    "main_ratio": "main_area_ratio", "under_ratio": "underground_ratio",
    "price": "sale_price_per_sqm_ils", "vat": "vat_rate",
    "build": "construction_cost_per_sqm_ils", "under_cost": "underground_cost_per_sqm_ils",
    "soft": "soft_cost_ratio", "demo": "demolition_cost_per_unit_ils",
    "avg_unit": "average_existing_unit_sqm", "comp": "tenant_compensation_sqm_per_existing_unit",
    "rent_months": "tenant_rent_months", "rent": "tenant_monthly_rent_ils",
    "moving": "tenant_moving_cost_ils", "legal": "tenant_legal_cost_per_unit_ils",
    "marketing": "marketing_ratio", "guarantees": "guarantees_ratio", "finance": "finance_ratio",
    "levy_rate": "betterment_levy_rate", "levy_base": "betterment_base_ils",
}
STATUS_LABEL = {"data": "נתון", "estimate": "אומדן", "missing": "חסר"}


def comparison_rows(econ: dict[str, Any]) -> list[tuple[str, Any, Any, str]]:
    """‏W2 · שורות ההשוואה בין שטח המדיניות לתקרת ה-400% — אותן שורות ב-PDF ובאקסל."""
    sc = econ.get("scenarios") or {}
    pol, cap = sc.get("policy") or {}, sc.get("cap_400") or {}
    return [
        ("שטח לבנייה (מ״ר)", pol.get("area_sqm"), cap.get("area_sqm"), "sqm"),
        ("אחוזי בנייה מהמגרש", pol.get("far_pct"), cap.get("far_pct"), "pct100"),
        ("שטח ליזם (מ״ר)", pol.get("developer_allocation_sqm"), cap.get("developer_allocation_sqm"), "sqm"),
        ("רווח לפני היטל (₪)", pol.get("profit_before_levy_ils"), cap.get("profit_before_levy_ils"), "ils"),
        ("תקרת היטל שמשאירה רווח מזערי (₪)", pol.get("levy_ceiling_ils"), cap.get("levy_ceiling_ils"), "ils"),
        ("אומדן היטל השבחה (₪)", pol.get("levy_estimate_ils"), cap.get("levy_estimate_ils"), "ils"),
        ("רווח אחרי אומדן היטל (₪)", pol.get("profit_after_levy_ils"), cap.get("profit_after_levy_ils"), "ils"),
        ("שיעור רווח על העלות, לפני היטל", pol.get("margin_before_levy"), cap.get("margin_before_levy"), "ratio"),
        ("שיעור רווח על העלות, אחרי אומדן היטל", pol.get("margin_after_levy"), cap.get("margin_after_levy"), "ratio"),
    ]


def _fmt(v: Any, kind: str) -> str:
    if v is None:
        return "—"
    if kind == "ratio":
        return f"{v:.1%}"
    if kind == "pct100":
        return f"{v:,.0f}%"
    return f"{v:,.0f}"


def _pdf_rights_comparison(econ: dict[str, Any], rights_: dict[str, Any], line) -> None:
    p = rights_.get("policy_area") or {}
    verdict = econ.get("rights_verdict") or {}
    line("זכויות לפי מדיניות הרצליה מול תקרת 400%", 11, (0.06, 0.15, 0.12), gap=4)
    if p.get("base"):
        b, lo, hi = p["base"], p["low"], p["high"]
        line(f'מגרש {p["plot_sqm"]:,.0f} מ״ר · מעטפת בתוך קווי הבניין {p["envelope_sqm"]:,.0f} מ״ר לקומה', 9, gap=2)
        if p.get("cap_400_sqm"):
            line(f'תקרת 400% (פי 4 מהשטח הבנוי הקיים): {p["cap_400_sqm"]:,.0f} מ״ר · '
                 f'{p["cap_400_far_pct"]:,.0f}% בנייה — תקרה בחוק, לא זכות', 9, gap=2)
        line(f'לפי המדיניות: {b["sqm"]:,.0f} מ״ר (טווח {lo["sqm"]:,.0f}–{hi["sqm"]:,.0f}) · '
             f'{b["far_pct"]:,.0f}% בנייה'
             + (f' · {b["share_of_cap"]:.0%} מהתקרה' if b.get("share_of_cap") is not None else ""), 9, gap=2)
        if b.get("gap_sqm") is not None:
            line(f'פער: {b["gap_sqm"]:,.0f} מ״ר · {b["gap_far_pct"]:,.0f} נקודות אחוזי בנייה · '
                 f'{b["unrealizable_share"]:.0%} מהזכויות אינן ניתנות למימוש לפי המדיניות', 9, gap=2)
        for lim in p.get("limits") or []:
            line(f"· {lim}", 8, (0.42, 0.40, 0.36), gap=1, indent=10)
        for asm in p.get("assumptions") or []:
            line(f"· הנחה: {asm}", 8, (0.42, 0.40, 0.36), gap=1, indent=10)
    elif p.get("why"):
        line(p["why"], 9, (0.54, 0.38, 0.00), gap=2)
    if econ.get("scenarios", {}).get("policy"):
        line("השוואה · לפי המדיניות מול 400%", 9.5, (0.06, 0.15, 0.12), gap=2)
        for label, pol, cap, kind in comparison_rows(econ):
            line(f"{label}: מדיניות {_fmt(pol, kind)} · תקרה {_fmt(cap, kind)}", 8.5, gap=1, indent=10)
    if verdict.get("text"):
        colour = (0.12, 0.37, 0.33) if verdict.get("case") == "A" else (0.54, 0.38, 0.00)
        line(verdict["text"], 9.5, colour, gap=5)


def _levy_unknown(econ: dict[str, Any]) -> bool:
    """בסיס ההשבחה אינו ידוע, ויש משפט תקרה להדפיס במקום ״0 ₪״."""
    base = (econ.get("assumptions") or {}).get("betterment_base_ils") or {}
    return base.get("status") == "missing" and bool((econ.get("betterment") or {}).get("summary"))


def _scenario_inputs(d: dict[str, Any]) -> dict[str, float | None]:
    a = d["economics"]["assumptions"]
    ident, rights_ = d["identity"], d["rights"]
    out: dict[str, float | None] = {
        "plot": ident.get("area_sqm"), "units": ident.get("existing_units"),
        # ‏W2 · השטח שעליו התרחיש מחושב: לפי המדיניות, ותקרת ה-400% רק כשאין.
        "buildable": d["economics"].get("buildable_area_sqm") or rights_.get("cap_400_sqm"),
    }
    out.update({key: (a[name]["value"] if name in a else None)
                for key, name in INPUT_ASSUMPTION.items()})
    # ‏B13 · בסיס השבחה שאינו ידוע הוא תא ריק, לא 0. אקסל מחשב תא ריק כ-0,
    # ולכן החישוב לא משתנה — משתנה מה שהיזם רואה: שאין כאן מספר.
    if (a.get("betterment_base_ils") or {}).get("status") == "missing":
        out["levy_base"] = None
    return out


def _input_provenance(d: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """לכל תא קלט: הסטטוס שלו ומאיפה הגיע. ‏B8 מצא 22 קלטים בלי מקור באקסל."""
    a = d["economics"]["assumptions"]
    out = {key: (STATUS_LABEL.get(a[name]["status"], a[name]["status"]), a[name].get("source") or "")
           for key, name in INPUT_ASSUMPTION.items() if name in a}
    evidence = {r["field"]: r for r in d.get("evidence") or []}
    for key, field in (("plot", "parcel_area"), ("units", "units")):
        r = evidence.get(field)
        if r:
            out[key] = (r.get("certainty_label") or r.get("certainty") or "",
                        " · ".join(x for x in (r.get("location"), r.get("method")) if x))
    rights_, econ = d["rights"], d["economics"]
    if econ.get("area_basis") == "policy":
        out["buildable"] = ("אומדן", econ.get("buildable_basis") or "")
    elif rights_.get("cap_400_sqm"):
        certainty = rights_.get("cap_400_certainty")
        out["buildable"] = ("אומדן" if certainty not in ("official", "derived", "manually_verified")
                            else "נגזר", rights_.get("cap_400_basis") or "")
    return out


def excel(d: dict[str, Any]) -> bytes:
    """שני גיליונות: ראיות, ותרחיש **עם נוסחאות חיות**.

    התוצאות אינן נכתבות כמספרים. יזם שמקבל טבלת תוצאות יכול רק להאמין
    לנו; יזם שמקבל נוסחאות משנה מחיר מכירה ורואה את המרווח זז.
    """
    import xlsxwriter

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "strings_to_urls": False})
    head = wb.add_format({"bold": True, "bg_color": "#14231F", "font_color": "white",
                          "text_wrap": True, "valign": "vcenter"})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    money = wb.add_format({"num_format": "#,##0"})
    ratio = wb.add_format({"num_format": "0.0%"})
    inp = wb.add_format({"font_color": "#1D4E89", "bg_color": "#F2F6FB", "num_format": "#,##0.###"})
    bold = wb.add_format({"bold": True, "num_format": "#,##0"})
    note = wb.add_format({"text_wrap": True, "font_color": "#6B655C", "valign": "top"})

    # ── ראיות ──
    ws = wb.add_worksheet("ראיות ומקורות")
    ws.right_to_left()
    ws.freeze_panes(1, 0)
    for col, width in enumerate((26, 20, 16, 12, 16, 46, 52)):
        ws.set_column(col, col, width)
    ws.write_row(0, 0, ["שדה", "ערך", "ודאות", "מכריע?", "נשלף", "מיקום בתוך המקור", "מקור"], head)
    for i, r in enumerate(d["evidence"], 1):
        ws.write_row(i, 0, [
            r.get("label") or r["field"], _v(r["value"]),
            r.get("certainty_label") or r["certainty"], "כן" if r["decides"] else "לא",
            (r.get("retrieved_at") or "")[:10], r.get("location") or "", r.get("source_url") or "",
        ], wrap)

    # ── תרחיש ──
    sc = wb.add_worksheet("תרחיש")
    sc.right_to_left()
    sc.set_column(0, 0, 34)
    sc.set_column(1, 1, 18)
    sc.set_column(2, 2, 26)
    sc.set_column(3, 3, 10)
    sc.set_column(4, 4, 70)
    sc.write_row(0, 0, ["קלט", "ערך", "יחידה", "סטטוס", "מקור"], head)

    values = _scenario_inputs(d)
    provenance = _input_provenance(d)
    for i, (key, lbl, unit) in enumerate(INPUT_ROWS):
        row = FIRST_INPUT_ROW + i
        sc.write(row, 0, lbl)
        v = values.get(key)
        if v is None:
            # ‏DOS-03: נתון חסר אינו אפס, ולכן התא ריק. **אקסל מחשב תא ריק
            # כ-0** — הנוסחאות לא יחזירו שגיאה. התא הריק אומר ליזם שאין כאן
            # מספר, ועמודת הסטטוס אומרת ״חסר״.
            sc.write_blank(row, 1, None, inp)
        else:
            sc.write_number(row, 1, v, inp)
        sc.write(row, 2, unit)
        status, source = provenance.get(key, ("", ""))
        sc.write(row, 3, status)
        sc.write(row, 4, source, note)

    out_start = FIRST_INPUT_ROW + len(INPUT_ROWS) + 2
    out_cell = {}
    sc.write_row(out_start - 1, 0, ["חישוב", "ערך", "יחידה", "", ""], head)
    for i, (key, _, _, _) in enumerate(OUTPUT_ROWS):
        out_cell[key] = f"B{out_start + i + 1}"

    refs = {**CELL, **out_cell}
    for i, (key, lbl, formula, unit) in enumerate(OUTPUT_ROWS):
        row = out_start + i
        fmt = ratio if unit == "%" else (bold if key in ("profit", "total_cost") else money)
        sc.write(row, 0, lbl, wb.add_format({"bold": key in ("profit", "margin")}))
        sc.write_formula(row, 1, formula.format(**refs), fmt)
        sc.write(row, 2, unit)

    econ = d["economics"]
    tail = out_start + len(OUTPUT_ROWS) + 2
    # ‏B8/B13 · הסייגים ומשפט ההיטל, מתחת לרווח ולא בגיליון אחר.
    lines = ([econ["profit_verdict"]] if econ.get("profit_verdict") else []) + \
            ([econ["rights_verdict"]["text"]] if (econ.get("rights_verdict") or {}).get("text") else []) + \
            ([econ["betterment"]["summary"]] if (econ.get("betterment") or {}).get("summary") else []) + \
            [cav["text"] for cav in econ.get("caveats") or []]
    if lines:
        sc.merge_range(tail, 0, tail, 4, "על מה הרווח נשען", head)
        for n, text in enumerate(lines, 1):
            sc.merge_range(tail + n, 0, tail + n, 4, text, note)
            sc.set_row(tail + n, 30)
        tail += len(lines) + 2

    # ‏B15 · התמהיל שהיזם חישב, אותו משפט כמו במסך וב-PDF.
    if (econ.get("unit_mix") or {}).get("summary"):
        sc.merge_range(tail, 0, tail, 4, "תמהיל דירות", head)
        sc.merge_range(tail + 1, 0, tail + 1, 4, econ["unit_mix"]["summary"], note)
        sc.set_row(tail + 1, 30)
        tail += 3

    sc.write(tail, 0, "הערות", head)
    sc.merge_range(tail + 1, 0, tail + 1, 4, econ["disclaimer"], note)
    sc.merge_range(tail + 2, 0, tail + 2, 4,
                   "התאים הכחולים הם קלטים — שינוי בהם מעדכן את כל החישוב. "
                   "תא ריק פירושו נתון שאינו ידוע, ולא אפס.", note)
    if not econ.get("is_deliverable", True):
        sc.merge_range(tail + 3, 0, tail + 3, 4,
                       econ.get("not_delivered_reason") or "התרחיש אינו נמסר כתוצאה.", note)
    v = d["versions"]
    sc.merge_range(tail + 4, 0, tail + 4, 4,
                   f'כללים {v["rules_version"]} · נתונים {v["data_version"] or "—"} · '
                   f'תבנית {v["template_version"]}', note)

    _excel_rights_sheet(wb, d, head, note, wrap)
    wb.close()
    return buf.getvalue()


def _excel_rights_sheet(wb, d: dict[str, Any], head, note, wrap) -> None:
    """‏W2 · גיליון ״מדיניות מול 400%״: השטח, הפער, ההשוואה הכלכלית ומה נדרש."""
    econ, p = d["economics"], d["rights"].get("policy_area") or {}
    ws = wb.add_worksheet("מדיניות מול 400%")
    ws.right_to_left()
    ws.set_column(0, 0, 44)
    ws.set_column(1, 2, 20)
    ws.set_column(3, 3, 70)
    num = wb.add_format({"num_format": "#,##0"})
    pct = wb.add_format({"num_format": "0.0%"})
    r = 0
    ws.merge_range(r, 0, r, 3, "זכויות לפי מדיניות הרצליה מול תקרת 400%", head)
    r += 1
    if p.get("base"):
        b, lo, hi = p["base"], p["low"], p["high"]
        rows = [
            ("שטח המגרש (מ״ר)", p.get("plot_sqm"), num, "שטח המגרש הקובע"),
            ("מעטפת בתוך קווי הבניין, לקומה (מ״ר)", p.get("envelope_sqm"), num, "אומדן בסיס"),
            ("תקרת 400% (מ״ר)", p.get("cap_400_sqm"), num, "פי 4 מהשטח הבנוי הקיים (§70ב) — תקרה בחוק, לא זכות"),
            ("תקרת 400% באחוזי בנייה מהמגרש", (p.get("cap_400_far_pct") or 0) / 100, pct, ""),
            ("שטח לפי המדיניות — בסיס (מ״ר)", b["sqm"], num, "התרחיש בגיליון ״תרחיש״ מחושב על המספר הזה"),
            ("שטח לפי המדיניות — נמוך (מ״ר)", lo["sqm"], num, "הכיוון הגרוע, בקומות המינימום"),
            ("שטח לפי המדיניות — גבוה (מ״ר)", hi["sqm"], num, "הכיוון הטוב, בקומות המקסימום"),
            ("אחוזי בנייה לפי המדיניות", (b.get("far_pct") or 0) / 100, pct, ""),
            ("פער מול התקרה (מ״ר)", b.get("gap_sqm"), num, ""),
            ("פער באחוזי בנייה", (b.get("gap_far_pct") or 0) / 100, pct, ""),
            ("שיעור הזכויות שאינו ניתן למימוש לפי המדיניות", b.get("unrealizable_share"), pct, ""),
        ]
        for label, value, fmt, why in rows:
            ws.write(r, 0, label)
            if value is None:
                ws.write_blank(r, 1, None)
            else:
                ws.write_number(r, 1, value, fmt)
            ws.write(r, 3, why, note)
            r += 1
        for title, items in (("גורמים מגבילים", p.get("limits") or []), ("הנחות", p.get("assumptions") or [])):
            r += 1
            ws.merge_range(r, 0, r, 3, title, head)
            r += 1
            for text in items:
                ws.merge_range(r, 0, r, 3, text, note)
                r += 1
    elif p.get("why"):
        ws.merge_range(r, 0, r, 3, p["why"], note)
        r += 1
    if (econ.get("scenarios") or {}).get("policy"):
        r += 1
        ws.write_row(r, 0, ["השוואה כלכלית", "לפי המדיניות", "תקרת 400%", ""], head)
        r += 1
        for label, pol, cap, kind in comparison_rows(econ):
            ws.write(r, 0, label)
            for col, v in ((1, pol), (2, cap)):
                if v is None:
                    ws.write(r, col, "—")
                elif kind == "pct100":
                    ws.write_number(r, col, v / 100, pct)
                else:
                    ws.write_number(r, col, v, pct if kind == "ratio" else num)
            r += 1
    verdict = econ.get("rights_verdict") or {}
    if verdict.get("text"):
        r += 1
        ws.merge_range(r, 0, r, 3, verdict["text"], wrap)
        ws.set_row(r, 45)
