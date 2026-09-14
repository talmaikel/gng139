# חלופת שקד · הרצליה

סריקת הזדמנויות להריסה ובנייה מחדש לפי תיקון 139 (§70א–§70ב), לעיריית הרצליה.

## 📅 תכנית העבודה

**[‏issue #6 · מעקב בטא](https://github.com/talmaikel/gng139/issues/6)** — התכנית הפעילה
והמקום **היחיד** שבו מסמנים. כל אחד מסמן את מה שסיים; ‏GitHub שומר מי ומתי, וכולם רואים מיד.

גרסה מעוצבת לקריאה: [שקדן · שני עד רביעי](https://claude.ai/code/artifact/a408d8dc-3e07-43ae-b3c1-9df27d89cd5a)
(דורשת חשבון Claude — **הסימון נעשה ב-issue, לא שם**).

## מי על מה

| זרם | מי | קבצים |
|---|---|---|
| **A** · המנוע והכללים | בועז | `cities/herzliya/`, `api/v1/candidates.py` |
| **B** · הכלכלה והנתונים | חן | `services/economic/`, `services/market_data/`, `api/v1/dossiers.py` |
| **C** · המסכים | טל | `frontend/src/` |

**קובץ אחד — בעלים אחד.** שני מקומות שכולם נוגעים בהם ודורשים הודעה מראש:
`alembic/versions/` ו-`requirements.txt`.

## מאיפה מתחילים

- **להריץ מקומית** — [`apps/shaked-engine/RUN_LOCAL.md`](apps/shaked-engine/RUN_LOCAL.md)
- **מה המוצר** — [`apps/shaked-engine/PRODUCT_STRUCTURE.md`](apps/shaked-engine/PRODUCT_STRUCTURE.md)
- **ההדגמה** — [`apps/shaked-engine/DEMO.md`](apps/shaked-engine/DEMO.md)

## שני מסמכים שאסור לעקוף

**[`POC/layer_a/data/DATA_LAW.md`](POC/layer_a/data/DATA_LAW.md)** — מה מותר לאסוף ומה
מותר לשמור. בקצרה: עובדות מותרות ללא הגבלה; הגרמושקה נמחקת אחרי החילוץ; שמות מבקשים
אינם נקראים מלכתחילה; ו**אין לסרוק את הארכיון** — תיקים נשלפים לפי בקשת לקוח, אחד-אחד.

**[`POC/layer_a/data/DOCUMENTS.md`](POC/layer_a/data/DOCUMENTS.md)** — מרשם מסמכי
המדיניות הקובעים, עם בדיקה חודשית אוטומטית. מכיל אזהרה על נוהל שעדיין מפורסם באתר
העירייה ושכבר אינו בתוקף — מי שיקרא אותו לבדו יפסול את כל המלאי בטעות.

## ‏POC

[`POC/`](POC/) הוא התייחסות בלבד, לא בסיס הפיתוח. הכל ב-`apps/shaked-engine`.

## תל אביב-יפו — הרחבה עתידית, לא בתחום העבודה

מה שנלמד מניסוי דוד המלך 23/25/27 מרוכז ב-
[`POC/data/cities/tel-aviv/README.md`](POC/data/cities/tel-aviv/README.md), ומה שנדרש
כדי להפעיל את תל אביב במנוע ב-
[`apps/shaked-engine/backend/app/cities/tel_aviv/README.md`](apps/shaked-engine/backend/app/cities/tel_aviv/README.md).
אין לפתח את זה עד להחלטה נפרדת.
