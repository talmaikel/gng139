/** עיצוב מספרים ותאריכים למסך. ה-PDF והאקסל מעצבים בשרת. */

// ‏`-0 ₪` על שורה שהיא אפס נראה כמו באג. אפס הוא אפס, וסימן המינוס
// שייך לסכום ולא לעיצוב.
export const ils = (n: number) =>
  Math.round(n) === 0 ? "0 ₪" : `${Math.round(n).toLocaleString("he-IL")} ₪`;

/** ‏#81 · סכומים גדולים במסך במיליונים. ‏31,126,961 ₪ עד השקל, על בסיס של
 *  שמונה-עשר אומדנים, נקרא כמו חשבון מדויק. ה-PDF והאקסל נשארים מדויקים —
 *  בדיקת המשטחים משווה אותם, והאקסל הוא המקום שהיזם מחשב בו. */
export const ilsApprox = (n: number) =>
  Math.abs(n) >= 1_000_000
    ? `${n < 0 ? "‎-" : ""}${(Math.abs(n) / 1e6).toLocaleString("he-IL", { maximumFractionDigits: 1 })} מיליון ₪`
    : ils(n);

export const sqm = (n: number) => `${Math.round(n).toLocaleString("he-IL")} מ״ר`;

export const dunam = (sqmValue: number) => `${(sqmValue / 1000).toFixed(1)} דונם`;

export const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("he-IL", { day: "numeric", month: "short", year: "numeric" }) : "—";
