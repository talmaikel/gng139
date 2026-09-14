/** תוויות תצוגה שאינן מגיעות מהשרת.
 *
 *  ‏FIELD_LABEL, ‏CERTAINTY_LABEL ו-ASSUMPTION_LABEL **הוסרו מכאן**: הם
 *  היו עותק שני של מפה שקיימת ב-`app/cities/herzliya/dossier.py`, והעותק
 *  נשר. ‏`betterment_levy_ratio` שונה בשרת ל-`betterment_levy_rate`,
 *  המפה כאן נשארה, ו-`label()` נפל בשקט חזרה למזהה הגולמי — כך שהיזם
 *  ראה `betterment_levy_rate` על המסך, בשורה שמסבירה למה אין לו תרחיש.
 *
 *  מה שנשאר כאן הוא מה שנושא **צבע** ולא רק טקסט: הצבע הוא החלטת עיצוב
 *  ואין לו מקום בשרת. הקבוצות עצמן סגורות וקטנות, ושינוי בהן הוא שינוי
 *  בסכמה שיישבר גם בטיפוסים. */

export const GATE_STATUS: Record<string, { label: string; colour: string; background: string }> = {
  passed: { label: "עבר", colour: "#1f5f55", background: "#eaf4f0" },
  failed: { label: "נכשל", colour: "#a8321e", background: "#fbeeea" },
  unknown: { label: "לא ידוע", colour: "#8a6100", background: "#fbf4e4" },
  routed: { label: "נותב למתחמים", colour: "#1d4e89", background: "#eaf0f9" },
  undefined: { label: "המדיניות שותקת", colour: "#5c5750", background: "#f0efec" },
  needs_measurement: { label: "דורש מדידה", colour: "#8a6100", background: "#fbf4e4" },
};

export const ASSUMPTION_STATUS: Record<string, { label: string; colour: string }> = {
  data: { label: "נתון", colour: "#1f5f55" },
  estimate: { label: "אומדן", colour: "#8a6100" },
  missing: { label: "חסר", colour: "#a8321e" },
};
