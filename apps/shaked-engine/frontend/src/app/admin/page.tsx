"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/brand/AppShell";
import { formatPrice } from "@/components/PurchaseDialog";
import {
  adminFindCompanies,
  adminGrantCredits,
  adminGrantHistory,
  ApiError,
  getMe,
  getPackages,
  type AdminCompany,
  type CreditGrantRow,
  type CreditPackage,
} from "@/lib/api";

/**
 * הוספת זכאות אחרי תשלום — הפיילוט, בלי סליקה.
 *
 * הסדר: הלקוח שילם בקישור → יצאה חשבונית ב-Morning → כאן מחפשים את החברה
 * לפי המייל, בוחרים חבילה, ורושמים את מספר החשבונית. בלי אסמכתה השרת מסרב.
 *
 * ‏**ההרשאה בשרת, לא כאן.** המסך מסתיר את עצמו ממי שאינו אדמין רק כדי שלא
 * יראה טופס שייכשל; ‏`/api/v1/admin/*` מחזיר 403 לכל מי שאינו `is_superuser`.
 */
export default function AdminPage() {
  const router = useRouter();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [q, setQ] = useState("");
  const [companies, setCompanies] = useState<AdminCompany[]>([]);
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [selected, setSelected] = useState<AdminCompany | null>(null);
  const [history, setHistory] = useState<CreditGrantRow[]>([]);
  const [packageId, setPackageId] = useState("");
  const [credits, setCredits] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    getMe()
      .then((me) => setAllowed(me.is_superuser))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/login");
        else setAllowed(false);
      });
    getPackages().then(setPackages).catch(() => setPackages([]));
  }, [router]);

  const search = useCallback(async (term: string) => {
    try {
      setCompanies(await adminFindCompanies(term));
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.detail : "החיפוש נכשל." });
    }
  }, []);

  useEffect(() => {
    if (allowed) search("");
  }, [allowed, search]);

  async function choose(company: AdminCompany) {
    setSelected(company);
    setMessage(null);
    setHistory(await adminGrantHistory(company.id).catch(() => []));
  }

  async function grant(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await adminGrantCredits(selected.id, {
        ...(packageId ? { package_id: packageId } : { credits: Number(credits) }),
        note,
      });
      setMessage({
        ok: true,
        text: `נוספו ${result.credits_added} ל${result.company}. יתרה: ${result.credits_remaining}.`,
      });
      setNote("");
      setCredits("");
      const updated = { ...selected, credits_remaining: result.credits_remaining };
      setSelected(updated);
      setCompanies((list) => list.map((c) => (c.id === updated.id ? updated : c)));
      setHistory(await adminGrantHistory(selected.id).catch(() => []));
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.detail : "ההוספה נכשלה." });
    } finally {
      setBusy(false);
    }
  }

  if (allowed === null) return <AppShell><p className="text-muted">טוען…</p></AppShell>;
  if (!allowed) {
    return (
      <AppShell>
        <div className="card auth-card">
          <h1>אין הרשאה</h1>
          <p>המסך הזה מיועד לצוות שקדן בלבד.</p>
          <Link href="/dashboard" className="text-link">חזרה</Link>
        </div>
      </AppShell>
    );
  }

  const amountChosen = packageId !== "" || Number(credits) > 0;

  return (
    <AppShell width={960}>
      <p className="eyebrow">חלופת שקד · ניהול</p>
      <h1 style={{ margin: ".15rem 0 .4rem" }}>הוספת זכאות</h1>
      <p className="text-muted" style={{ marginTop: 0, fontSize: ".92rem" }}>
        אחרי שהתשלום התקבל והחשבונית יצאה. כל הוספה נרשמת עם האסמכתה ועם מי שהוסיף.
      </p>

      <form
        onSubmit={(e) => { e.preventDefault(); search(q); }}
        style={{ display: "flex", gap: ".6rem", margin: "1rem 0", flexWrap: "wrap" }}
      >
        <input
          aria-label="חיפוש חברה"
          placeholder="שם חברה או מייל של משתמש"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ flex: "1 1 240px" }}
        />
        <button type="submit">חיפוש</button>
      </form>

      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <div className="card" style={{ padding: ".6rem", overflowX: "auto" }}>
          {companies.length === 0 && <p style={{ margin: ".4rem" }}>לא נמצאו חברות.</p>}
          {companies.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => choose(c)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "start",
                margin: ".2rem 0",
                background: selected?.id === c.id ? "var(--almond-soft)" : "var(--paper)",
                color: "var(--ink)",
                border: `1px solid ${selected?.id === c.id ? "var(--almond)" : "var(--rule)"}`,
                fontWeight: 400,
              }}
            >
              <strong>{c.name}</strong> · יתרה {c.credits_remaining}
              <br />
              <span dir="ltr" style={{ fontSize: ".82rem" }}>{c.emails.join(", ") || "—"}</span>
            </button>
          ))}
        </div>

        <div className="card">
          {!selected ? (
            <p style={{ margin: 0 }}>בחרו חברה מהרשימה.</p>
          ) : (
            <>
              <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>
                {selected.name} · יתרה {selected.credits_remaining}
              </h2>
              <form onSubmit={grant}>
                <div className="form-field">
                  <label htmlFor="package">חבילה</label>
                  <select id="package" value={packageId} onChange={(e) => setPackageId(e.target.value)}>
                    <option value="">— מספר חופשי —</option>
                    {packages.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} · {formatPrice(p)}
                      </option>
                    ))}
                  </select>
                </div>
                {packageId === "" && (
                  <div className="form-field">
                    <label htmlFor="credits">מספר הזדמנויות</label>
                    <input
                      id="credits"
                      type="number"
                      min={1}
                      max={1000}
                      value={credits}
                      onChange={(e) => setCredits(e.target.value)}
                    />
                  </div>
                )}
                <div className="form-field">
                  <label htmlFor="note">אסמכתה (מספר חשבונית / תשלום)</label>
                  <input id="note" required minLength={2} value={note} onChange={(e) => setNote(e.target.value)} />
                </div>
                <button type="submit" disabled={busy || !amountChosen}>
                  {busy ? "מוסיף…" : "הוספת זכאות"}
                </button>
              </form>

              {message && (
                <p className={message.ok ? "text-ok" : "text-bad"} style={{ fontSize: ".9rem" }}>{message.text}</p>
              )}

              <h3 style={{ fontSize: ".95rem", marginBottom: ".3rem" }}>היסטוריה</h3>
              {history.length === 0 ? (
                <p className="text-muted" style={{ margin: 0, fontSize: ".88rem" }}>לא נוספה זכאות עדיין.</p>
              ) : (
                <ul style={{ margin: 0, paddingInlineStart: "1.1rem", fontSize: ".88rem" }}>
                  {history.map((h, i) => (
                    <li key={i}>
                      +{h.credits} · {h.note} · {h.granted_by ?? "?"} ·{" "}
                      {h.created_at ? new Date(h.created_at).toLocaleDateString("he-IL") : ""}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
