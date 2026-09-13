# שבעת מסכי ה-PRD מול מה שקיים

‏C1. סקר, לא מימוש — נכתב כדי שמי שלוקח את ציר ג' יתחיל לבנות ולא לסקור.
נכון ל-13.09.2026.

## מה קיים היום

‏197 שורות בסך הכל:

| קובץ | מה הוא עושה |
|---|---|
| `app/login/page.tsx` | התחברות, שומר JWT ב-`localStorage` |
| `app/dashboard/page.tsx` | מפה + טבלת מועמדים |
| `components/Map.tsx` | Leaflet, מצייר את פוליגון החלקה האמיתי, מתאים זום אוטומטית |
| `lib/api.ts` | `login`, `getCandidates` |

## המיפוי

| # | מסך ב-PRD §7 | מצב | מה חסר |
|---|---|---|---|
| 1 | **לוח בקרה** | ❌ חסר | חבילות, יתרות, תיקים שנמסרו, הפקות בתהליך. **גם ה-API חסר** — ראה `C13` |
| 2 | **מפת חיפוש** | ◐ חלקי | המפה קיימת ומציגה פוליגונים אמיתיים. חסר: **ציור** פוליגון, טופס תנאי חובה, **סדר העדפות**, והצגת מגבלת השטח. הצד השרתי כבר מוכן — `POST /candidates/{city}/search` |
| 3 | **רכישת חבילה** | ❌ חסר | מסך ו-API. `C13` |
| 4 | **תוצאות חבילה** | ◐ חלקי | יש טבלה, אבל היא של *כל* המועמדים ולא של חבילה. חסר: **נימוק בחירה** (`A6`), יתרה, כפתור השלמה |
| 5 | **תיק הזדמנות** | ❌ חסר | אין תצוגת תיק כלל. הצד השרתי קיים: `POST /dossiers/{id}/generate` ו-`GET /dossiers/status/{task}` |
| 6 | **רכישת שריון** | — | **מחוץ להיקף הבטא** במכוון |
| 7 | **מאגר החברה** | — | **מחוץ להיקף הבטא** במכוון |

## שני דברים שכדאי לתקן לפני שבונים מסך חדש

**‏1. `Candidate` ב-`api.ts` אינו מכיר את `assessment`.** השדה נוסף היום לשרת ומכיל את מה שהמשתמש באמת צריך — סטטוס, טווח הקומות ואם הוא ודאי, תקרת 400% והוודאות שלה, ואילו שערים חוסמים. בלי להוסיף אותו לטיפוס, המסך לא יכול להציג כלום מזה.

```ts
assessment: {
  status: "eligible" | "needs_verification" | "urban_renewal_compound" | "ineligible";
  floors_low: number | null; floors_high: number | null;
  floors_certain: boolean; case_by_case: boolean;
  cap_400_sqm: number | null; cap_400_certainty: string | null;
  blocking: string[]; deliverable: boolean;
} | null;
```

**‏2. הטבלה מציגה `verification_level`, והוא תמיד `raw`.** זה נכון טכנית — הוא מתאר איך נתון הושג, וכל הנתונים שלנו נקראו משכבות GIS בלי OCR ובלי אדם. אבל **למשתמש זה נראה כאילו שום דבר לא נבדק.** מה שהוא צריך לראות במקום זה `assessment.status`.

## נקודות חיבור מוכנות

```
POST /api/v1/candidates/{city}/search    ← פוליגון מצויר, מחזיר את מי שבתוכו
     body: {polygon, min_area_sqm?, deliverable_only?, limit}
     422 עם הודעה בעברית לפוליגון פסול, חורג או מחוץ לעיר
GET  /api/v1/candidates/{city}?deliverable_only=true
GET  /api/v1/filters/options
POST /api/v1/dossiers/{id}/generate  ·  GET /api/v1/dossiers/status/{task}
POST /api/v1/economic/feasibility
```

**המפה כבר מקבלת `geometry` ו-`centroid` לכל מועמד** — אין צורך לחשב מרכז בצד הלקוח.
