"""קריטריון היציאה של A10: שדה שהופשט ממקורו חייב להפיל בדיקה.

סוויטה ירוקה אינה מוכיחה שהיא שומרת על משהו. הסקריפט הזה משנה את הקוד
בכוונה — מוריד את בדיקת המיקום, מתיר לראיית OCR להכריע, מבטל את חסם הגיל —
ומריץ את הסוויטה. מוטציה ש**שורדת** היא בדיקה שחסרה.

    python tests/mutations.py $(which python)

אינו חלק מ-pytest: הוא כותב לקבצי המקור וזורק אותם חזרה, ואין להריץ אותו
במקביל לעצמו.
"""
import shutil, subprocess, sys, pathlib
MUTS = [
  ("evidence.py", "שדה בלי מיקום עדיין מכריע",
   'and field.get("location") is not None', "and True"),
  ("evidence.py", "שדה בלי כתובת מקור מכריע",
   'if not source.get("url") or not source.get("retrieved_at"):', "if False:"),
  ("evidence.py", "ראיית OCR רשאית להכריע",
   'field.get("certainty") not in DECIDING', "False"),
  ("evidence.py", "ערך ריק מכריע",
   'field.get("value") is None', "False"),
  ("evidence.py", "גיל המקור אינו חוסם",
   "age_days <= max_age_days", "True"),
  ("evidence.py", "תאריך שליפה עתידי מתקבל",
   "0 <= age_days", "True"),
  ("cities/herzliya/seed_layer_a.py", "שדה בלי מקור נכתב בכל זאת",
   "if not src or not location:", "if False:"),
  ("cities/herzliya/seed_layer_a.py", "ערך חסר נכתב כ-OFFICIAL",
   "certainty, method = Certainty.MISSING, method", "certainty, method = certainty, method"),
  ("services/evidence_store.py", "שדות שאינם מכריעים נכנסים להכרעה",
   "if usable(f, get_settings().source_max_age_days, now)}", "if True}"),
  # ‏B14 · שלושת המשטחים
  ("cities/herzliya/exports.py", "האקסל אינו כותב את המחיר לחלקה",
   '"price": "sale_price_per_sqm_ils",', '"price": "sale_price_per_sqm_ils_city",'),
  # ‏B13 · הייצוא אומר מה הוא לא יודע
  ("cities/herzliya/exports.py", "שורת ההיטל ב-PDF חוזרת ל-0 ₪",
   'if key == "betterment_levy_ils" and _levy_unknown(econ):', 'if False:'),
  ("cities/herzliya/exports.py", "הסייגים לא נכנסים לאקסל",
   '[cav["text"] for cav in econ.get("caveats") or []]', '[]'),
  ("cities/herzliya/exports.py", "ה-PDF מדפיס רווח שאינו הרווח",
   '''line(f'רווח: {s["projected_profit_ils"]:,.0f} ₪''',
   '''line(f'רווח: {s["projected_profit_ils"] * 1.02:,.0f} ₪'''),
  # ‏P1 · מחיר דירה חדשה לפי גוש
  ("cities/herzliya/dossier.py", "התיק מתעלם מטבלת הגושים",
   "price, block_label = new_build_prices.sale_price(opp.block, a.sale_price_per_sqm_ils.value)",
   "price, block_label = a.sale_price_per_sqm_ils.value, None"),
  # ‏E1 · רווח מזערי 16%, ושיווק ומימון לא על דירות הבעלים
  ("services/economic/calculator.py", "שיווק מחושב שוב על דירות הבעלים",
   "total_marketing_ils = developer_revenue_ils * inputs.marketing_ratio",
   "total_marketing_ils = total_revenue_ils * inputs.marketing_ratio"),
  ("services/economic/calculator.py", "מימון מחושב שוב על שווי דירות הבעלים",
   "total_finance_ils = (cost_before_finance - land_cost_ils) * inputs.finance_ratio",
   "total_finance_ils = cost_before_finance * inputs.finance_ratio"),
  ("cities/herzliya/dossier.py", "תקרת ההיטל חוזרת לרווח אפס",
   "return r.projected_profit_ils - target * r.total_cost_ils", "return r.projected_profit_ils"),
  # ‏B15 · מחיר יד שנייה אינו מחיר מכירה, והתמהיל נכתב בכל משטח
  ("cities/herzliya/dossier.py", "מחיר יד שנייה משוקלל נכנס להכנסות",
   'and valuation.price_basis == "new_build"):', '):'),
  ("cities/herzliya/exports.py", "התמהיל לא נכנס לאקסל",
   'sc.merge_range(tail + 1, 0, tail + 1, 4, econ["unit_mix"]["summary"], note)', 'pass'),
  ("services/unit_mix/service.py", "מסך התמהיל מתמחר לפי מחיר אחר מהתיק",
   "price_per_sqm_ils=sale_price_per_sqm_ils,", "price_per_sqm_ils=sale_price_per_sqm_ils * 0.76,"),
  # ‏W4 · ״מכריע״ בתיק הוא אותו כלל שמכריע את השערים
  ("cities/herzliya/dossier.py", "״מכריע״ בתיק חוזר לבדוק ודאות בלבד",
   '"decides": usable(f, get_settings().source_max_age_days),', '"decides": f.get("certainty") in DECIDING,'),
  # ‏W1 · השטח לפי מדיניות הרצליה, בתוך קווי הבניין
  ("cities/herzliya/policy_envelope.py", "הנסיגות אינן מצטברות מהקומה שמתחת",
   "[(1.0, s, 0.0), (1.0, 2 * s, s)]", "[(1.0, s, 0.0), (1.0, s, s)]"),
  ("cities/herzliya/policy_envelope.py", "כל המעטפת נחשבת בנויה (בלי η)",
   "v = ETA * sqm", "v = sqm"),
  ("cities/herzliya/policy_envelope.py", "מגרש פינתי נבדק כחזית אחת",
   "chosen = corner if frontages >= 2 else single", "chosen = single"),
  ("cities/herzliya/rules.py", "התיק אינו מחשב שטח לפי מדיניות",
   'out["policy_area"] = policy.as_dict() if policy else {"why": policy_why}',
   'out["policy_area"] = {"why": policy_why}'),
  # ‏A24 · קצב לשרתי הגרמושקות, ומשותף לכל התהליך
  ("sources/client.py", "הגרמושקות יורדות בלי קצב",
   '"archive.gis-net.co.il": HostPolicy(min_interval_seconds=10.0),', ''),
  ("sources/client.py", "כל לקוח חדש מאפס את הקצב",
   "self._slots = slots if slots is not None else SHARED_SLOTS", "self._slots = slots if slots is not None else HostSlots()"),
  # ‏W10 · יחס המגורים מטבלת השטחים בהיתר מכריע את שער ה-70%
  ("cities/herzliya/rights.py", "שער ה-70% עובר על כל יחס",
   "RESIDENTIAL_SHARE_MIN = 0.7", "RESIDENTIAL_SHARE_MIN = 0.0"),
  ("services/residential_share.py", "הזנה ידנית נכתבת כקריאה שאינה מכריעה",
   "certainty=Certainty.MANUALLY_VERIFIED,", "certainty=Certainty.AI_CANDIDATE,"),
  ("services/residential_share.py", "הזנה שנייה נערמת על הראשונה",
   "await session.execute(delete(FieldEvidence).where(", "await session.execute(select(FieldEvidence).where("),
  ("cities/herzliya/rules.py", "השער עובר בלי לומר על מה נשען",
   'd["residential_share_basis"] = rights.share_basis(f["residential_share"])',
   'd["residential_share_basis"] = None'),
]
root = pathlib.Path("app")
# ‏**עד 14.09 הסקריפט רק הדפיס.** מוטציה ששרדה הדפיסה ״X שרד״, והשלב ב-CI
# נשאר ירוק — כלומר בדיקה שנמחקה או נחלשה לא הייתה עוצרת דבר. גם ביטוי
# שלא נמצא נכשל: הקוד זז, והמוטציה בודקת עכשיו אוויר.
failed = []
for rel, name, old, new in MUTS:
    p = root / rel
    src = p.read_text(encoding="utf-8")
    if old not in src:
        print(f"  ?  {name}: הביטוי לא נמצא"); failed.append(name); continue
    shutil.copy(p, "/tmp/bak.py")
    p.write_text(src.replace(old, new, 1), encoding="utf-8")
    r = subprocess.run([sys.argv[1], "-m", "pytest", "-q", "-x", "--no-header"],
                       capture_output=True, text=True)
    shutil.copy("/tmp/bak.py", p)
    print(f"  {'V נתפס' if r.returncode else 'X שרד '}  {name}")
    if not r.returncode:
        failed.append(name)
sys.exit(1 if failed else 0)

