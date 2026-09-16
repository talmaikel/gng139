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
 *  בסכמה שיישבר גם בטיפוסים.
 *
 *  הצבע הוא **טון**: ‏ok (ירוק) עבר / נתון, ‏warn (כתום השקד) דורש אימות /
 *  אומדן, ‏bad (אדום) נכשל / חסר, ‏neutral (אפור) אינו אומר דבר. הערכים
 *  ההקסדצימליים כאן זהים ל-`--ok-*` וחבריהם ב-`globals.css`. */

export type Tone = "ok" | "warn" | "bad" | "neutral";

export const TONE_COLOUR: Record<Tone, { colour: string; background: string }> = {
  ok: { colour: "#1f5a3c", background: "#dcefe3" },
  warn: { colour: "#c96f33", background: "#fdeee3" },
  bad: { colour: "#a2402e", background: "#f5e4e0" },
  neutral: { colour: "#5b6068", background: "#ebedf1" },
};

type Status = { label: string; tone: Tone; colour: string; background: string };
const status = (label: string, tone: Tone): Status => ({ label, tone, ...TONE_COLOUR[tone] });

export const GATE_STATUS: Record<string, Status> = {
  passed: status("עבר", "ok"),
  failed: status("נכשל", "bad"),
  unknown: status("לא ידוע", "warn"),
  routed: status("נותב למתחמים", "neutral"),
  undefined: status("המדיניות שותקת", "neutral"),
  needs_measurement: status("דורש מדידה", "warn"),
};

export const ASSUMPTION_STATUS: Record<string, Status> = {
  data: status("נתון", "ok"),
  estimate: status("אומדן", "warn"),
  missing: status("חסר", "bad"),
};

export const ASSESSMENT_STATUS: Record<string, Status> = {
  eligible: status("כשיר", "ok"),
  needs_verification: status("דורש אימות", "warn"),
  urban_renewal_compound: status("מסלול מתחמים", "neutral"),
  ineligible: status("אינו כשיר", "bad"),
};

/** ‏Leaflet מצייר בקנבס וצריך צבע ממשי, לא משתנה CSS. */
export const MAP_COLOUR = {
  candidate: "#E8894A",
  selected: "#13161E",
  area: "#13161E",
  tooLarge: "#A2402E",
};
