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
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/alembic upgrade head        # צריך להגיע ל-0004_merge_heads
.venv/bin/python -m pytest -q         # 51 עוברות
.venv/bin/uvicorn app.main:app --port 8000
```

## Frontend

```bash
cd apps/shaked-engine/frontend
npm install
npx next dev -p 3000
```

## המלכודת בהרשמה

`POST /api/v1/auth/register` דורש `company_id` של חברה **קיימת**, ולכן הרשמה
ראשונה נכשלת ב-422 עד שיש שורה ב-`tenants`. בנוסף, כתובת בדומיין
`.test`/`.local` נדחית בוולידציה.

```bash
CID=$(psql -d shaked_engine -tAc \
  "INSERT INTO tenants (id,name,slug,is_active,created_at)
   VALUES (gen_random_uuid(),'Dev Co','dev-co',true,now()) RETURNING id" | tr -d '[:space:]')

curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' \
  -d "{\"email\":\"dev@shaked.example.com\",\"password\":\"devpass12345\",
       \"full_name\":\"Dev\",\"company_id\":\"$CID\"}"
```

ואז login ב-`/api/v1/auth/jwt/login` עם `username`/`password` כ-form-urlencoded.

## מה נבדק

| | |
|---|---|
| `alembic upgrade head` | ראש יחיד `0004_merge_heads` |
| `pytest` | 51 עוברות |
| `POST /auth/register` | 201 |
| `POST /auth/jwt/login` | JWT |
| `GET /candidates/herzliya` | 200 · `[]` — **אין עדיין הזדמנויות זרועות** |
| `GET /filters/options` | 200 · הרצליה ות״א |
| `GET /` ו-`/login` בפרונט | 200 |

הרשימה הריקה אינה תקלה: זריעת 700 המועמדים מ-`layer_a` היא משימה A1.
