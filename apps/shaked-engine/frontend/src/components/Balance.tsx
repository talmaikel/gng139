"use client";

import type { AccountBalance, CreditPackage } from "@/lib/api";

interface Props {
  balance: AccountBalance | null;
  packages: CreditPackage[];
  /** נשאר בחתימה: המסך קורא לו אחרי מסירה. אין כאן עוד פעולה שמשנה יתרה. */
  onChanged?: () => void;
}

/**
 * ‏`mailto:` או `https://wa.me/972…`. בלי ערך — הכפתור אינו מוצג ונשאר משפט.
 * כתובת אמיתית אינה נכתבת בקוד: היא של העסק, והיא משתנה.
 */
const SALES_CONTACT_URL = process.env.NEXT_PUBLIC_SALES_CONTACT_URL ?? "";

/** ההודעה שהלקוח שולח כוללת את מזהה החברה — כך האדמין מוצא אותה בלי לנחש. */
function contactHref(balance: AccountBalance | null): string {
  if (!SALES_CONTACT_URL) return "";
  const text = `שלום, אשמח לרכוש חבילת הזדמנויות בשקדן.${
    balance ? `\nמזהה חברה: ${balance.company_id}` : ""
  }`;
  if (SALES_CONTACT_URL.startsWith("mailto:")) {
    const sep = SALES_CONTACT_URL.includes("?") ? "&" : "?";
    return `${SALES_CONTACT_URL}${sep}subject=${encodeURIComponent("רכישת חבילה · שקדן")}&body=${encodeURIComponent(text)}`;
  }
  if (SALES_CONTACT_URL.includes("wa.me/")) {
    return `${SALES_CONTACT_URL}?text=${encodeURIComponent(text)}`;
  }
  return SALES_CONTACT_URL;
}

/**
 * הזכאות של החברה, ולא של המשתמש.
 *
 * ה-PRD מפורש: *״הזכאות לשלוש הזדמנויות שייכת לחברה ומשותפת לצוותה״*
 * ו*״תוצאה שנמסרה למשתמש בחברה נחשבת תוצאה שנמסרה לחברה״*. הניסוח כאן
 * בגוף החברה ולא בגוף המשתמש, כי מי שיראה ״נותרו לך 2״ ויגלה שעמית
 * הוריד אותם יחשוב שנגנב ממנו משהו.
 *
 * ‏**אין כאן כפתור רכישה.** בפיילוט הלקוח משלם בקישור ומקבל חשבונית, ואדמין
 * מוסיף זכאות ב-`/admin`. כפתור שהוסיף זכאות בלחיצה נתן תיקים בחינם לכל נרשם.
 */
export default function Balance({ balance, packages }: Props) {
  const remaining = balance?.credits_remaining ?? 0;
  const delivered = balance?.delivered_count ?? 0;
  const empty = remaining === 0;
  const href = contactHref(balance);

  return (
    <div
      className="card"
      style={{
        padding: "0.85rem 1.1rem",
        display: "flex",
        gap: "1rem",
        alignItems: "center",
        flexWrap: "wrap",
        borderColor: empty ? "#e6d8b8" : undefined,
        background: empty ? "#fdfaf1" : undefined,
      }}
    >
      <strong style={{ fontSize: "1.05rem", color: empty ? "#8a6100" : "#1f5f55" }}>
        {empty ? "לא נותרה זכאות לחברה"
          : remaining === 1 ? "נותרה הזדמנות אחת לחברה"
          : `נותרו ${remaining} הזדמנויות לחברה`}
      </strong>

      <span style={{ color: "#6b655c", fontSize: ".88rem" }}>
        {delivered === 0 ? "טרם נמסר דבר" : `${delivered} כבר נמסרו · הגישה משותפת לכל הצוות`}
      </span>

      <span style={{ flex: 1 }} />

      {packages.length > 0 && (
        <span style={{ color: "#6b655c", fontSize: ".88rem" }}>
          {packages
            .map((p) => `${p.name} · ${p.price_ils.toLocaleString("he-IL")} ₪`)
            .join("  ·  ")}
        </span>
      )}

      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="button"
          style={{
            background: "#1d4e89",
            color: "white",
            padding: ".45rem .9rem",
            borderRadius: 6,
            textDecoration: "none",
            fontSize: ".92rem",
          }}
        >
          לרכישה צרו קשר
        </a>
      ) : (
        <span style={{ fontSize: ".88rem" }}>לרכישת חבילה צרו קשר עם צוות שקדן</span>
      )}
    </div>
  );
}
