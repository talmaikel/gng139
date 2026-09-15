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
  # ‏A24 · קצב לשרתי הגרמושקות, ומשותף לכל התהליך
  ("sources/client.py", "הגרמושקות יורדות בלי קצב",
   '"archive.gis-net.co.il": HostPolicy(min_interval_seconds=10.0),', ''),
  ("sources/client.py", "כל לקוח חדש מאפס את הקצב",
   "self._slots = slots if slots is not None else SHARED_SLOTS", "self._slots = slots if slots is not None else HostSlots()"),
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

