# חלופת שקד · הרצליה

סריקת הזדמנויות להריסה ובנייה מחדש לפי תיקון 139 (§70א–§70ב), לעיריית הרצליה.

## 📅 תכנית העבודה

**[שקדן · שני עד רביעי](https://claude.ai/code/artifact/a408d8dc-3e07-43ae-b3c1-9df27d89cd5a)**
— התכנית הפעילה. הערכת מצב, 22 משימות עם בעלים, וסימונים משותפים בזמן אמת.

[תכנית יום ראשון](https://claude.ai/code/artifact/43132667-b4e2-47de-801c-993550525904)
נשמרה כארכיון. **אל תעבדו לפיה.**

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
