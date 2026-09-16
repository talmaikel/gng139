"use client";

import { useEffect, useState } from "react";
import { ApiError, purchasePackage, type CreditPackage, type PaymentMethod } from "@/lib/api";

/**
 * ‏**תשלום מדומה** (טל, 16.09): לחיצה על אמצעי תשלום מוסיפה את זכאות החבילה
 * מיד, כאילו התשלום עבר. השרת מאפשר את זה רק כשהוא רץ עם
 * `SIMULATED_PAYMENTS=true`; אחרת הוא מחזיר 404, והחלון חוזר לזרימת הפיילוט:
 * פרטי קשר, תשלום בקישור, ואדמין מוסיף זכאות ב-`/admin`.
 *
 * הטלפון והמייל מגיעים מ-`.env.local` ולא מהקוד: הריפו ציבורי.
 */
const PHONE = process.env.NEXT_PUBLIC_SALES_PHONE ?? "";
const EMAIL = process.env.NEXT_PUBLIC_SALES_EMAIL ?? "";

const CONTACT_LINK: React.CSSProperties = {
  display: "block", padding: ".55rem .8rem", borderRadius: 5, border: "1px solid var(--rule)",
  textDecoration: "none", color: "var(--ink)", background: "var(--ground)", fontWeight: 600,
};

const METHODS: { id: PaymentMethod; label: string }[] = [
  { id: "card", label: "כרטיס אשראי" },
  { id: "bit", label: "Bit" },
  { id: "paypal", label: "PayPal" },
];

export const formatPrice = (p: CreditPackage) =>
  `${p.price_ils.toLocaleString("he-IL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₪`;

/** ‏0543088827 → ‏972543088827, כפי ש-wa.me מצפה. */
function whatsappNumber(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  return digits.startsWith("0") ? `972${digits.slice(1)}` : digits;
}

interface Props {
  pkg: CreditPackage;
  companyId: string | null;
  onClose: () => void;
  /** נקרא אחרי שהזכאות נוספה, כדי שהמסך ירענן את היתרה */
  onPurchased?: () => void;
}

type State =
  | { kind: "choose" }
  | { kind: "paying"; method: PaymentMethod }
  | { kind: "done"; added: number; remaining: number }
  | { kind: "offline"; method: PaymentMethod }
  | { kind: "error"; text: string };

export default function PurchaseDialog({ pkg, companyId, onClose, onPurchased }: Props) {
  const [state, setState] = useState<State>({ kind: "choose" });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function pay(method: PaymentMethod) {
    setState({ kind: "paying", method });
    try {
      const r = await purchasePackage(pkg.id, method);
      setState({ kind: "done", added: r.credits_added, remaining: r.credits_remaining });
      onPurchased?.();
    } catch (e) {
      // 404 = השרת בלי תשלום מדומה: זרימת הפיילוט, פרטי קשר.
      if (e instanceof ApiError && e.status === 404) setState({ kind: "offline", method });
      else setState({ kind: "error", text: e instanceof ApiError ? e.detail : "התשלום לא הושלם. אפשר לנסות שוב." });
    }
  }

  const method = state.kind === "offline" ? state.method : null;
  const methodLabel = METHODS.find((m) => m.id === method)?.label ?? "";
  // ״בכרטיס אשראי״ אבל ״ב-Bit״: לפני מילה לועזית בא מקף.
  const viaMethod = /^[A-Za-z]/.test(methodLabel) ? `ב-${methodLabel}` : `ב${methodLabel}`;
  // מזהה החברה בהודעה — כך האדמין מוצא אותה ב-/admin בלי לנחש.
  const message =
    `שלום, אשמח לרכוש את חבילת ${pkg.name} (${formatPrice(pkg)}) בשקדן, בתשלום ${viaMethod}.` +
    (companyId ? `\nמזהה חברה: ${companyId}` : "");

  return (
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(19, 22, 30, .5)", zIndex: 2000,
        display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="purchase-title"
        className="card"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 420, margin: 0 }}
      >
        <h2 id="purchase-title" style={{ marginTop: 0, fontSize: "1.15rem" }}>
          רכישת {pkg.name} · {formatPrice(pkg)}
        </h2>

        {(state.kind === "choose" || state.kind === "paying" || state.kind === "error") && (
          <>
            <p className="text-muted" style={{ margin: "0 0 .8rem", fontSize: ".92rem" }}>בחרו אמצעי תשלום</p>
            <div style={{ display: "grid", gap: ".5rem" }}>
              {METHODS.map((m) => (
                <button key={m.id} type="button" className="btn-secondary" disabled={state.kind === "paying"}
                        onClick={() => pay(m.id)}>
                  {state.kind === "paying" && state.method === m.id ? "מעבד תשלום…" : m.label}
                </button>
              ))}
            </div>
            {state.kind === "error" && <p className="text-bad" style={{ margin: ".8rem 0 0", fontSize: ".9rem" }}>{state.text}</p>}
          </>
        )}

        {state.kind === "done" && (
          <div className="card tone-ok" style={{ padding: ".9rem 1rem" }}>
            <strong className="text-ok" style={{ fontSize: "1.05rem" }}>
              התשלום התקבל · נוספו {state.added} הזדמנויות
            </strong>
            <p style={{ margin: ".3rem 0 0", fontSize: ".92rem" }}>
              יתרת החברה עכשיו: <strong>{state.remaining}</strong>. אפשר לחזור למפה ולחפש.
            </p>
          </div>
        )}

        {state.kind === "offline" && (
          <>
            <p style={{ margin: "0 0 .6rem" }}>
              <strong>התשלום באתר ייפתח בקרוב.</strong> בינתיים נשלח לכם קישור לתשלום {viaMethod},
              והזכאות תתווסף לחברה מיד אחרי שהתשלום יתקבל.
            </p>
            {PHONE || EMAIL ? (
              <div style={{ display: "grid", gap: ".5rem" }}>
                {PHONE && (
                  <a style={CONTACT_LINK} target="_blank" rel="noopener noreferrer"
                     href={`https://wa.me/${whatsappNumber(PHONE)}?text=${encodeURIComponent(message)}`}>
                    וואטסאפ · <span dir="ltr">{PHONE}</span>
                  </a>
                )}
                {PHONE && (
                  <a style={CONTACT_LINK} href={`tel:${PHONE}`}>
                    שיחה · <span dir="ltr">{PHONE}</span>
                  </a>
                )}
                {EMAIL && (
                  <a style={CONTACT_LINK}
                     href={`mailto:${EMAIL}?subject=${encodeURIComponent(`רכישת ${pkg.name} · שקדן`)}&body=${encodeURIComponent(message)}`}>
                    מייל · <span dir="ltr">{EMAIL}</span>
                  </a>
                )}
              </div>
            ) : (
              <p>צרו קשר עם צוות שקדן.</p>
            )}
            <button type="button" className="btn-link" onClick={() => setState({ kind: "choose" })} style={{ marginTop: ".8rem" }}>
              ← אמצעי תשלום אחר
            </button>
          </>
        )}

        <div style={{ textAlign: "end", marginTop: ".8rem" }}>
          <button type="button" className={state.kind === "done" ? undefined : "btn-secondary"} onClick={onClose}>
            {state.kind === "done" ? "לחיפוש" : "סגירה"}
          </button>
        </div>
      </div>
    </div>
  );
}
