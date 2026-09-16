"use client";

import { useEffect, useState } from "react";
import { ApiError, getMe, requestVerification, type Me } from "@/lib/api";

/**
 * תזכורת לאמת את המייל. **אינה חוסמת דבר** — מי שנרשם כבר עובד.
 * האימות שם כדי שמי שנרשם במייל של מישהו אחר לא יישאר בלי שנדע.
 */
export default function VerifyEmailNotice() {
  const [me, setMe] = useState<Me | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  if (!me || me.is_verified) return null;

  async function resend() {
    if (!me) return;
    setBusy(true);
    try {
      await requestVerification(me.email);
      setStatus("נשלח קישור אימות חדש.");
    } catch (e) {
      setStatus(e instanceof ApiError ? e.detail : "השליחה נכשלה.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card tone-info" style={{ padding: ".6rem 1rem", marginBottom: "1rem", fontSize: ".9rem",
                                   display: "flex", gap: ".8rem", alignItems: "center", flexWrap: "wrap" }}>
      <span>
        כדאי לאמת את כתובת המייל: שלחנו קישור אל <span dir="ltr">{me.email}</span>
      </span>
      <button type="button" className="btn-link" onClick={resend} disabled={busy}>
        {busy ? "שולח…" : "שליחה חוזרת"}
      </button>
      {status && <span className="text-muted">{status}</span>}
    </div>
  );
}
