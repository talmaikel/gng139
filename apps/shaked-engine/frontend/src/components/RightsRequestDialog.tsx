"use client";

import { useEffect } from "react";

interface Props {
  /** כמה חלקות באזור כלכליות רק עם הגדלת זכויות. מספר בלבד — בלי כתובות. */
  count: number;
  /** כמה תיקים יימסרו אם הלקוח מאשר: עד שלושה, ולא יותר מהיתרה. */
  offer: number;
  busy: boolean;
  onAccept: () => void;
  onOtherArea: () => void;
  onClose: () => void;
}

/**
 * ‏W6 · הדילמה (בועז, 16.09): באזור אין אף חלקה כלכלית לפי המדיניות, והלקוח
 * סימן ״כלול חלקות שכלכליות רק עם הגדלת זכויות״.
 *
 * השרת לא מסר, לא חייב ולא חשף כתובת. **הכתובת היא המוצר**, ולכן הלקוח מחליט
 * לפני שהוא רואה אותה: לאשר ולקבל (חיוב), או לחפש אזור אחר (בלי חיוב).
 */
export default function RightsRequestDialog({ count, offer, busy, onAccept, onOtherArea, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const parcels = count === 1 ? "חלקה אחת" : `${count} חלקות`;
  const files = offer === 1 ? "תיק אחד" : `${offer} תיקים`;

  return (
    <div
      role="presentation"
      onClick={() => !busy && onClose()}
      style={{
        position: "fixed", inset: 0, background: "rgba(19, 22, 30, .5)", zIndex: 2000,
        display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rights-title"
        className="card"
        onClick={(e) => e.stopPropagation()}
        style={{ width: "100%", maxWidth: 440, margin: 0 }}
      >
        <h2 id="rights-title" style={{ marginTop: 0, fontSize: "1.15rem" }}>
          באזור אין חלקה כלכלית לפי המדיניות
        </h2>
        <p style={{ margin: "0 0 .5rem", fontSize: ".92rem" }}>
          יש באזור <strong>{parcels}</strong> שכלכליות רק אם תתקבל הגדלת זכויות מעבר למדיניות. זה לא מובטח,
          והתיק יראה כמה זכויות צריך להוסיף.
        </p>
        <p className="text-muted" style={{ margin: "0 0 1rem", fontSize: ".88rem" }}>
          <strong>לא חויבת ולא נחשפו כתובות.</strong> אישור מוסר {files}, וכל תיק מנכה זכאות אחת.
        </p>

        <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button type="button" className="btn-secondary" onClick={onOtherArea} disabled={busy}>
            לחפש אזור אחר
          </button>
          <button type="button" onClick={onAccept} disabled={busy || offer < 1}>
            {busy ? "מאתר תיקים…" : "לאשר ולקבל"}
          </button>
        </div>
      </div>
    </div>
  );
}
