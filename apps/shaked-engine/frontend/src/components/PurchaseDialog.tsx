"use client";

import { useEffect, useState } from "react";
import type { CreditPackage } from "@/lib/api";

/**
 * ‏**אמצעי התשלום אינם מחוברים לשום דבר.** בפיילוט הלקוח בוחר חבילה ואמצעי,
 * ומקבל את פרטי הקשר; התשלום עצמו נעשה בקישור ששולחים לו, ואדמין מוסיף
 * זכאות ב-`/admin`. כשתחובר סליקה אמיתית — היא נכנסת במקום פרטי הקשר.
 *
 * הטלפון והמייל מגיעים מ-`.env.local` ולא מהקוד: הריפו ציבורי.
 */
const PHONE = process.env.NEXT_PUBLIC_SALES_PHONE ?? "";
const EMAIL = process.env.NEXT_PUBLIC_SALES_EMAIL ?? "";

const CONTACT_LINK: React.CSSProperties = {
  display: "block", padding: ".55rem .8rem", borderRadius: 5, border: "1px solid var(--rule)",
  textDecoration: "none", color: "var(--ink)", background: "var(--ground)", fontWeight: 600,
};

type Method = "card" | "bit" | "paypal";

const METHODS: { id: Method; label: string }[] = [
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
}

export default function PurchaseDialog({ pkg, companyId, onClose }: Props) {
  const [method, setMethod] = useState<Method | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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

        {!method ? (
          <>
            <p className="text-muted" style={{ margin: "0 0 .8rem", fontSize: ".92rem" }}>בחרו אמצעי תשלום</p>
            <div style={{ display: "grid", gap: ".5rem" }}>
              {METHODS.map((m) => (
                <button key={m.id} type="button" className="btn-secondary" onClick={() => setMethod(m.id)}>
                  {m.label}
                </button>
              ))}
            </div>
          </>
        ) : (
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
            <button type="button" className="btn-link" onClick={() => setMethod(null)} style={{ marginTop: ".8rem" }}>
              ← אמצעי תשלום אחר
            </button>
          </>
        )}

        <div style={{ textAlign: "end", marginTop: ".8rem" }}>
          <button type="button" className="btn-secondary" onClick={onClose}>סגירה</button>
        </div>
      </div>
    </div>
  );
}
