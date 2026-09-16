"use client";

import { useState } from "react";
import type { AccountBalance, CreditPackage } from "@/lib/api";
import PurchaseDialog, { formatPrice } from "@/components/PurchaseDialog";

interface Props {
  balance: AccountBalance | null;
  packages: CreditPackage[];
  /** נשאר בחתימה: המסך קורא לו אחרי מסירה. אין כאן עוד פעולה שמשנה יתרה. */
  onChanged?: () => void;
}

/**
 * הזכאות של החברה, ולא של המשתמש.
 *
 * ה-PRD מפורש: *״הזכאות לשלוש הזדמנויות שייכת לחברה ומשותפת לצוותה״*
 * ו*״תוצאה שנמסרה למשתמש בחברה נחשבת תוצאה שנמסרה לחברה״*. הניסוח כאן
 * בגוף החברה ולא בגוף המשתמש, כי מי שיראה ״נותרו לך 2״ ויגלה שעמית
 * הוריד אותם יחשוב שנגנב ממנו משהו.
 *
 * ‏**כפתור חבילה אינו מוסיף זכאות.** הוא פותח את חלון הרכישה, ששם אמצעי
 * התשלום עוד אינם מחוברים (`PurchaseDialog`). הזכאות מתווספת ב-`/admin`.
 */
export default function Balance({ balance, packages }: Props) {
  const [chosen, setChosen] = useState<CreditPackage | null>(null);
  const remaining = balance?.credits_remaining ?? 0;
  const delivered = balance?.delivered_count ?? 0;
  const empty = remaining === 0;

  return (
    <div
      className={`card${empty ? " tone-warn" : ""}`}
      style={{ padding: "0.85rem 1.1rem", display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap" }}
    >
      <strong className={empty ? "text-warn" : "text-ok"} style={{ fontSize: "1.05rem" }}>
        {empty ? "לא נותרה זכאות לחברה"
          : remaining === 1 ? "נותרה הזדמנות אחת לחברה"
          : `נותרו ${remaining} הזדמנויות לחברה`}
      </strong>

      <span className="text-muted" style={{ fontSize: ".88rem" }}>
        {delivered === 0 ? "טרם נמסר דבר" : `${delivered} כבר נמסרו · הגישה משותפת לכל הצוות`}
      </span>

      <span style={{ flex: 1 }} />

      {packages.map((p) => (
        <button key={p.id} type="button" className="btn-secondary btn-sm" onClick={() => setChosen(p)}>
          {p.name} · {formatPrice(p)}
        </button>
      ))}

      {chosen && (
        <PurchaseDialog pkg={chosen} companyId={balance?.company_id ?? null} onClose={() => setChosen(null)} />
      )}
    </div>
  );
}
