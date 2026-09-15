"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
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

  if (allowed === null) return <main className="page"><p>טוען…</p></main>;
  if (!allowed) {
    return (
      <main className="page">
        <div className="card" style={{ maxWidth: 420, margin: "3.5rem auto" }}>
          <h1 style={{ marginTop: 0 }}>אין הרשאה</h1>
          <p>המסך הזה מיועד לצוות שקדן בלבד.</p>
          <Link href="/dashboard">חזרה</Link>
        </div>
      </main>
    );
  }

  const amountChosen = packageId !== "" || Number(credits) > 0;

  return (
    <main className="page" style={{ maxWidth: 960, margin: "0 auto" }}>
      <p style={{ margin: 0, color: "#6b655c", fontSize: ".82rem", letterSpacing: ".08em" }}>
        חלופת שקד · ניהול
      </p>
      <h1 style={{ margin: ".15rem 0 .4rem" }}>הוספת זכאות</h1>
      <p style={{ marginTop: 0, color: "#6b655c", fontSize: ".92rem" }}>
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
                background: selected?.id === c.id ? "#1f5f55" : "#f3efe7",
                color: selected?.id === c.id ? "white" : "#14231f",
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
                        {p.name} · {p.credits} הזדמנויות · {p.price_ils.toLocaleString("he-IL")} ₪
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
                <p style={{ color: message.ok ? "#1f5f55" : "#a8321e", fontSize: ".9rem" }}>{message.text}</p>
              )}

              <h3 style={{ fontSize: ".95rem", marginBottom: ".3rem" }}>היסטוריה</h3>
              {history.length === 0 ? (
                <p style={{ margin: 0, fontSize: ".88rem", color: "#6b655c" }}>לא נוספה זכאות עדיין.</p>
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
    </main>
  );
}
