"use client";

import { useState } from "react";
import { ApiError, purchasePackage, type AccountBalance, type CreditPackage } from "@/lib/api";

interface Props {
  balance: AccountBalance | null;
  packages: CreditPackage[];
  onChanged: () => void;
}

/**
 * הזכאות של החברה, ולא של המשתמש.
 *
 * ה-PRD מפורש: *״הזכאות לשלוש הזדמנויות שייכת לחברה ומשותפת לצוותה״*
 * ו*״תוצאה שנמסרה למשתמש בחברה נחשבת תוצאה שנמסרה לחברה״*. הניסוח כאן
 * בגוף החברה ולא בגוף המשתמש, כי מי שיראה ״נותרו לך 2״ ויגלה שעמית
 * הוריד אותם יחשוב שנגנב ממנו משהו.
 */
export default function Balance({ balance, packages, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remaining = balance?.credits_remaining ?? 0;
  const delivered = balance?.delivered_count ?? 0;
  const empty = remaining === 0;

  async function buy(id: string) {
    setBusy(true);
    setError(null);
    try {
      await purchasePackage(id);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "הרכישה נכשלה.");
    } finally {
      setBusy(false);
    }
  }

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
        {empty ? "לא נותרה זכאות לחברה" : `נותרו ${remaining} הזדמנויות לחברה`}
      </strong>

      <span style={{ color: "#6b655c", fontSize: ".88rem" }}>
        {delivered === 0 ? "טרם נמסר דבר" : `${delivered} כבר נמסרו · הגישה משותפת לכל הצוות`}
      </span>

      <span style={{ flex: 1 }} />

      {packages.map((p) => (
        <button key={p.id} onClick={() => buy(p.id)} disabled={busy} style={{ background: "#1d4e89" }}>
          {p.name} · {p.price_ils.toLocaleString("he-IL")} ₪
        </button>
      ))}

      {error && <span style={{ color: "#a8321e", fontSize: ".88rem" }}>{error}</span>}
    </div>
  );
}
