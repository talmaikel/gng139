# הרצה מקומית — macOS

נבדק מקצה לקצה ב-13.09.2026. ה-`PRODUCT_STRUCTURE.md` מתאר התקנת Windows;
זה המסלול ל-Mac.

## דרישות

```bash
brew install postgresql@17 postgis node
brew services start postgresql@17
```

## בסיס נתונים — פעם אחת

```bash
psql -d postgres -c "CREATE ROLE shaked LOGIN PASSWORD 'shaked' SUPERUSER"
psql -d postgres -c "CREATE DATABASE shaked_engine OWNER shaked"
psql -d shaked_engine -c "CREATE EXTENSION IF NOT EXISTS postgis"
```

## Backend

```bash
cd apps/shaked-engine/backend
# ‏--seed חשוב: בלעדיו אין pip **בתוך** ה-venv, ו-`pip install` יפעיל את
# ה-pip של המערכת — יצהיר הצלחה, והחבילה לא תהיה שם. זה קרה, פעמיים.
uv venv --python 3.12 --seed .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
cp .env.example .env
.venv/bin/alembic upgrade head        # צריך להגיע ל-0007_add_market_data
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --port 8000
```

**Postgres מקומי בלי docker** (טל, Windows, 15.09): למשתמש `shaked` אין הרשאת
CREATEDB, ולכן הבדיקות לא יוצרות לבד את מסד הבדיקות ו-113 מהן מדלגות בשקט.
פעם אחת, ממשתמש `postgres`:

```bash
createdb -U postgres -O shaked shaked_engine_test
psql -U postgres -d shaked_engine_test -c "CREATE EXTENSION postgis"
```

**חברת ההדגמה במסד נקי** — אין אותה אחרי זריעה. ‏`demo_setup.py` יוצר אותה, והסיסמה
נשאלת ולא מודפסת:

```bash
.venv/bin/python scripts/demo_setup.py --apply
```

ב-Windows הנתיב הוא `.venv\Scripts\python` במקום `.venv/bin/python`.

## Frontend

```bash
cd apps/shaked-engine/frontend
npm install
npx next dev -p 3000
```

## משתמש ראשון

דרך המסך: `http://localhost:3000/signup`. או ישירות — ההרשמה פותחת חברה חדשה,
הנרשם הוא ה-owner שלה, והתשובה כבר מכילה טוקן:

```bash
curl -X POST localhost:8000/api/v1/auth/signup -H 'Content-Type: application/json' \
  -d '{"company_name":"Dev Co","full_name":"Dev","email":"dev@shaked.example.com","password":"devpass12345"}'
```

כתובת בדומיין `.test`/`.local` נדחית בוולידציה. ‏`/auth/register` הישן **הוסר**:
הוא קיבל `company_id` ו-`role` מהגולש, כלומר כל אחד יכול היה להצטרף לחברה
קיימת כ-owner.

כניסה חוזרת: `/api/v1/auth/jwt/login` עם `username`/`password` כ-form-urlencoded.

## זכאות: אין רכישה באתר

בפיילוט אין סליקה. הלקוח לוחץ ״לרכישה צרו קשר״ (היעד ב-`NEXT_PUBLIC_SALES_CONTACT_URL`),
משלם בקישור Bit עסקי / PayPal, ומקבל חשבונית ב-Morning. אז אדמין נכנס ל-`/admin`,
מוצא את החברה לפי מייל, ומוסיף זכאות עם מספר החשבונית. כל הוספה נרשמת ב-`credit_grants`.

אדמין הוא משתמש רגיל שהוגדר מהשרת — אין לזה נתיב באתר:

```bash
.venv/bin/python scripts/make_admin.py you@example.com --apply
```

## מה נבדק

| | |
|---|---|
| `alembic upgrade head` | ראש יחיד `0004_merge_heads` |
| `pytest` | 51 עוברות |
| `POST /auth/signup` | 201 |
| `POST /auth/jwt/login` | JWT |
| `GET /candidates/herzliya` | 200 · `[]` — **אין עדיין הזדמנויות זרועות** |
| `GET /filters/options` | 200 · הרצליה ות״א |
| `GET /` ו-`/login` בפרונט | 200 |

הרשימה הריקה אינה תקלה: זריעת 700 המועמדים מ-`layer_a` היא משימה A1.

## התיישנות מקורות — החלטה, לא הגדרה

`SOURCE_MAX_AGE_DAYS = 30`. שדה שמקורו נשלף לפני יותר מכך **מפסיק להכריע
בשקט**: אין שגיאה, פשוט מפסיקים להיות מועמדים כשירים. זו התנהגות נכונה
ומסוכנת גם יחד, כי ביום שהיא תתרחש היא תיראה בדיוק כמו באג.

מקורות שכבה א׳ נשלפו ב-12–13.09.2026, ולכן הם **פגים סביב 12.10**.

`app/services/evidence_store.stale_fields()` מחזירה את השדות שהיו מכריעים
אלמלא גילם — להריץ אותה לפני כל הדגמה, לא אחריה.

**מה עושים כשזה קורה:** מריצים מחדש את `POC/layer_a/scripts/fetch_sources.py`
ואז את הזורע. זו הרצה של דקות, לא של יום.

**למה לא פשוט להעלות את הסף:** כי המספר אינו שרירותי — שכבות עירוניות
משתנות. שכבת החלקות אפילו מדווחת על עצמה: `SYS_DATE` שלה נע בין 2020 ל-2026,
והוא נשמר עכשיו ב-`field_evidence.source_updated_at`. **גיל השליפה שלנו
וגיל הנתון במקור הם שני דברים שונים**, והעמודה הזו היא מה שיאפשר בעתיד
להחליט לפי השני ולא רק לפי הראשון.

## אם הסביבה מתנהגת מוזר

הסימן: ‏`pip install` מדווח הצלחה, ו-`import` נכשל.

```bash
.venv/bin/python --version     # איזו גרסה רצה
.venv/bin/pip --version        # ולאיזו pip שייך — חייבות להיות זהות
ls .venv/lib/                  # חייבת להיות תיקייה אחת בלבד
```

שלוש בדיקות ב-`tests/test_environment.py` אוכפות את זה, ונכשלות עם הוראות
התיקון. אם הן נכשלות — לבנות מחדש, זה שלושים שניות:

```bash
rm -rf .venv && uv venv --python 3.12 --seed .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
```

**‏`requirements.txt` מספיק בפני עצמו** — נבדק: venv נקי ממנו בלבד מריץ את
כל 251 הבדיקות.
