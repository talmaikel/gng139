# מדריך לקולגה: הפעלת Shakdan POC ב־Windows

המדריך מיועד למי שכבר קיבל גישה לריפו ועשה `pull` או `clone`. המסלול המומלץ לפיילוט הוא הפעלה מקומית עם SQLite. הוא אינו דורש Docker, PostgreSQL או מפתח OpenAI.

## 1. מה צריך להתקין פעם אחת

- **Git** — למשיכת הריפו.
- **Python 3.12 בגרסת 64-bit** — בזמן ההתקנה יש לסמן `Add Python to PATH`.
- **Microsoft Edge** — Playwright משתמש ב־Edge שכבר מותקן ב־Windows. אין צורך להוריד Chromium בנפרד.
- **Tesseract OCR עם `heb` ו־`eng`** — נדרש רק לסריקת מסמכים. האתר עצמו יעלה גם בלעדיו. מומלץ מתקין Windows של UB Mannheim ובחירת Hebrew ו־English בזמן ההתקנה.

Docker Desktop הוא אפשרות מתקדמת בלבד למי שרוצה לבדוק PostgreSQL/PostGIS.

## 2. אחרי כל `git pull`

יש לפתוח PowerShell בתיקיית הריפו ולעבור לתיקיית ה־POC:

```powershell
cd POC
```

בהפעלה הראשונה, או כאשר `requirements.txt` השתנה, מריצים:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
```

הסקריפט מבצע את הפעולות הבאות:

1. בודק שגרסת Python מתאימה.
2. יוצר סביבה מקומית בשם `.venv`.
3. מתקין את כל חבילות Python, כולל FastAPI ו־Playwright.
4. בודק שנמצאו Edge ו־Tesseract עם עברית ואנגלית.
5. מריץ את בדיקות התקינות של הפרויקט.

אין צורך להריץ `playwright install`: הקוד משתמש ב־Microsoft Edge המקומי.

## 3. הפעלת ה־POC

להפעלה רגילה, כאשר חלון PowerShell נשאר פתוח:

```powershell
.\start.ps1
```

לאחר מכן פותחים:

- ממשק: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- בדיקת בריאות: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- תיעוד API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

תגובה תקינה מבדיקת הבריאות תיראה כך:

```json
{"status":"ok","database":"sqlite-local"}
```

להפעלה ברקע:

```powershell
.\start-background.ps1
```

הפקודה מציגה מספר תהליך ושומרת לוגים תחת `data`. אם פורט 8000 כבר תפוס, אין להפעיל עותק נוסף של השרת.

## 4. בדיקה ידנית ראשונה

לאחר שהאתר נפתח:

1. ודאו שהלוגו Shakdan והמפה מוצגים.
2. לחצו **פתיחת התיק המנותח** ובדקו את תיק השושנים 4.
3. לחצו **פתיחת בדיקת 10 המבנים** ובדקו את דוח המקורות.
4. בחרו מרכז לדוגמה והריצו סריקת רדיוס. שלב זה תלוי בגישה למקורות הציבוריים בזמן אמת.

תיקי הדוגמה והראיות שנשמרו בריפו זמינים גם כאשר אתר העירייה אינו זמין. סריקה חדשה דורשת חיבור אינטרנט וגישה פעילה למקורות העירוניים ול־GovMap.

## 5. בדיקת Playwright ו־OCR

בדיקת שפות OCR:

```powershell
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs
```

ברשימה חייבים להופיע:

```text
eng
heb
```

ניסוי OCR מקומי, ללא עלות API:

```powershell
.venv\Scripts\python.exe scripts\run_local_hashoshanim_ocr.py
```

בדיקת איסוף קטנה מהארכיון, עם שמירת checkpoint:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\sync_herzliya_archive.py discover --limit 10
.venv\Scripts\python.exe -X utf8 scripts\sync_herzliya_archive.py hydrate --limit 10
.venv\Scripts\python.exe -X utf8 scripts\sync_herzliya_archive.py status
```

Playwright ו־Tesseract אינם שירותי API ואינם יוצרים חיוב. אין לעקוף CAPTCHA, התחברות או חסימת גישה. אם העירייה מחזירה `429`, עוצרים וממשיכים מאוחר יותר; הנתונים שכבר נשמרו לא אובדים.

## 6. מידע מקומי שאינו עובר ב־Git

כל מחשב מקבל בסיס נתונים מקומי חדש בקובץ `data/shaked.sqlite3`. הקובץ, המטמון, מסמכים חדשים ותוצרי ניסוי אינם עוברים ב־Git. לכן מונה התיקים והחיפושים במחשב החדש עשויים להתחיל מאפס.

כן עוברים ב־Git:

- קוד ה־POC והעיצוב.
- תיקי הדוגמה שכבר צורפו לפרויקט.
- הראיות השמורות של השושנים 4.
- דוח בדיקת 10 המבנים.
- חוקי ה־pipeline והחלטות המוצר.

אין להעביר `OPENAI_API_KEY` או סודות אחרים דרך Git. במסלול הנוכחי, המבוסס Playwright ו־Tesseract, אין צורך במפתח OpenAI.

## 7. פתרון תקלות נפוצות

### `python` אינו מזוהה

מתקינים Python 3.12, מסמנים `Add Python to PATH`, סוגרים ופותחים מחדש את PowerShell.

### הרצת סקריפטים חסומה

אפשר להריץ את סקריפט ההכנה עם:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
```

### `tesseract` אינו מזוהה

הקוד מחפש גם ב־`C:\Program Files\Tesseract-OCR\tesseract.exe`. אם הקובץ אינו קיים, מתקינים מחדש את Tesseract עם חבילת השפה Hebrew.

### פורט 8000 תפוס

כנראה שה־POC כבר פועל. פותחים [http://127.0.0.1:8000](http://127.0.0.1:8000). אם נדרש שרת חדש, סוגרים קודם את התהליך הישן.

### המפה עולה אבל גבול העיר או סריקה חדשה נכשלים

זוהי בדרך כלל חסימת רשת או תקלה זמנית במקור הציבורי. תיקי הדוגמה המקומיים עדיין אמורים להיפתח. יש לנסות שוב מאוחר יותר בלי למחוק את `data/shaked.sqlite3`.

### איפוס מלא של ההתקנה המקומית

סוגרים את השרת, מוחקים ידנית את `.venv` ואת `data/shaked.sqlite3`, ואז מריצים שוב את סקריפט ההכנה. מחיקת בסיס הנתונים מוחקת את החיפושים והאינדקס שנאספו באותו מחשב.

## 8. מסלול PostGIS אופציונלי

למי שמותקן אצלו Docker Desktop:

```powershell
docker compose up --build
```

מסלול זה מפעיל את האתר ואת PostgreSQL/PostGIS ומוסיף Tesseract בתוך הקונטיינר. מסלול הדפדפן העירוני של Playwright עדיין מיועד להפעלה המקומית ב־Windows עם Edge, ולכן לצורך הניסוי הנוכחי עדיף להתחיל במסלול SQLite שבסעיפים הקודמים.

