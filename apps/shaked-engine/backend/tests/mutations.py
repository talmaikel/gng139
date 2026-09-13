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
]
root = pathlib.Path("app")
for rel, name, old, new in MUTS:
    p = root / rel
    src = p.read_text(encoding="utf-8")
    if old not in src:
        print(f"  ?  {name}: הביטוי לא נמצא"); continue
    shutil.copy(p, "/tmp/bak.py")
    p.write_text(src.replace(old, new, 1), encoding="utf-8")
    r = subprocess.run([sys.argv[1], "-m", "pytest", "-q", "-x", "--no-header"],
                       capture_output=True, text=True)
    shutil.copy("/tmp/bak.py", p)
    print(f"  {'V נתפס' if r.returncode else 'X שרד '}  {name}")

