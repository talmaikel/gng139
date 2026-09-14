"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

type UnitRow = {
  id: string;
  source_key: string;
  unit_label: string | null;
  floor: string | null;
  area_sqm: number | null;
  certainty: string;
  requires_human_review: boolean;
  source_url: string | null;
  retrieved_at: string | null;
  location: string | null;
  method: string | null;
  raw_text: string | null;
};

type ReviewState = {
  opportunity_id: string;
  address: string;
  municipal_unit_count: number | null;
  units: UnitRow[];
  resolution: {
    average_existing_unit_sqm: number | null;
    source: string;
    certainty: string;
    per_unit_detail_available: boolean;
    unit_count: number | null;
    schedule_complete: boolean;
    has_unit_count_conflict: boolean;
    may_decide: boolean;
    notes: string[];
  };
};

type Draft = { unit_label: string; floor: string; area_sqm: string };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = window.localStorage.getItem("shaked_token");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401) throw new Error("AUTH");
  if (!response.ok) {
    let detail = "הפעולה נכשלה.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch { /* no-op */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function draftFor(unit: UnitRow): Draft {
  return {
    unit_label: unit.unit_label ?? "",
    floor: unit.floor ?? "",
    area_sqm: unit.area_sqm == null ? "" : String(unit.area_sqm),
  };
}

export default function DwellingUnitReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [state, setState] = useState<ReviewState | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const sync = (next: ReviewState) => {
    setState(next);
    setDrafts(Object.fromEntries(next.units.map((u) => [u.id, draftFor(u)])));
  };

  useEffect(() => {
    api<ReviewState>(`/api/v1/dossiers/${id}/dwelling-units`)
      .then(sync)
      .catch((e) => {
        if (e instanceof Error && e.message === "AUTH") { router.replace("/login"); return; }
        setError(e instanceof Error ? e.message : "לא ניתן לטעון את הדירות.");
      });
  }, [id, router]);

  async function review(unit: UnitRow, action: "confirm" | "reject") {
    const draft = drafts[unit.id] ?? draftFor(unit);
    setSaving(unit.id);
    setError(null);
    try {
      const body = action === "confirm" ? {
        action,
        unit_label: draft.unit_label || null,
        floor: draft.floor || null,
        area_sqm: draft.area_sqm === "" ? null : Number(draft.area_sqm),
      } : { action };
      const next = await api<ReviewState>(
        `/api/v1/dossiers/${id}/dwelling-units/${unit.id}`,
        { method: "PATCH", body: JSON.stringify(body) },
      );
      sync(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "לא ניתן לשמור את הבדיקה.");
    } finally {
      setSaving(null);
    }
  }

  if (!state) {
    return <main className="page"><p>{error ?? "טוען…"}</p></main>;
  }

  const r = state.resolution;

  return (
    <main className="page" style={{ maxWidth: 1050 }} dir="rtl">
      <p style={{ margin: "0 0 .8rem" }}>
        <Link href={`/dossier/${id}`} style={{ color: "#6b655c" }}>← חזרה לתיק</Link>
      </p>
      <h1 style={{ marginBottom: ".2rem" }}>אימות שטחי הדירות</h1>
      <p style={{ marginTop: 0, color: "#6b655c" }}>
        {state.address} · ספירה עירונית: {state.municipal_unit_count ?? "—"} דירות
      </p>

      <section className="card" style={{ marginBottom: "1rem" }}>
        <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>מצב הלוח</h2>
        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
          <div><small>שורות עם שטח</small><br /><strong>{r.unit_count ?? 0}</strong></div>
          <div><small>ממוצע מאומת</small><br /><strong>{r.average_existing_unit_sqm == null ? "—" : `${r.average_existing_unit_sqm} מ״ר`}</strong></div>
          <div><small>לוח שלם</small><br /><strong>{r.schedule_complete ? "כן" : "לא"}</strong></div>
          <div><small>רשאי להכריע תרחיש</small><br />
            <strong style={{ color: r.may_decide ? "#1f5f55" : "#8a6100" }}>{r.may_decide ? "כן" : "לא"}</strong>
          </div>
        </div>
        {r.has_unit_count_conflict && (
          <p style={{ color: "#a8321e", fontWeight: 600 }}>יש סתירה בין מספר הדירות בלוח לבין הספירה העירונית.</p>
        )}
        {r.notes.map((note) => <p key={note} style={{ color: "#6b655c", fontSize: ".84rem" }}>{note}</p>)}
      </section>

      {error && <div className="card" style={{ marginBottom: "1rem", color: "#a8321e" }}>{error}</div>}

      {state.units.length === 0 ? (
        <section className="card">
          <strong>עדיין אין שורות דירה לחוות עליהן דעה.</strong>
          <p>יש להריץ קודם את יצירת התיק כדי שמנוע B3 יחלץ את לוח הדירות מהגרמושקה.</p>
        </section>
      ) : (
        <section className="card" style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr><th>דירה</th><th>קומה</th><th>שטח</th><th>מצב</th><th>מקור</th><th>פעולה</th></tr>
            </thead>
            <tbody>
              {state.units.map((unit) => {
                const d = drafts[unit.id] ?? draftFor(unit);
                const verified = !unit.requires_human_review && unit.certainty === "manually_verified";
                return (
                  <tr key={unit.id}>
                    <td><input value={d.unit_label} onChange={(e) => setDrafts((x) => ({ ...x, [unit.id]: { ...d, unit_label: e.target.value } }))} style={{ width: 80 }} /></td>
                    <td><input value={d.floor} onChange={(e) => setDrafts((x) => ({ ...x, [unit.id]: { ...d, floor: e.target.value } }))} style={{ width: 80 }} /></td>
                    <td><input type="number" min="15" max="400" step="0.01" value={d.area_sqm} onChange={(e) => setDrafts((x) => ({ ...x, [unit.id]: { ...d, area_sqm: e.target.value } }))} style={{ width: 100 }} /> מ״ר</td>
                    <td style={{ fontWeight: 600, color: verified ? "#1f5f55" : "#8a6100" }}>
                      {verified ? "אומת ידנית" : unit.method === "manual_rejected" ? "נדחה — חילוץ מחדש" : "דורש בדיקה"}
                    </td>
                    <td>
                      {unit.source_url ? <a href={unit.source_url} target="_blank" rel="noreferrer" style={{ color: "#1d4e89" }}>פתח מסמך</a> : "אין מקור"}
                      {unit.location && <div style={{ color: "#6b655c", fontSize: ".78rem", maxWidth: 260 }}>{unit.location}</div>}
                      {unit.raw_text && <div style={{ color: "#6b655c", fontSize: ".75rem", maxWidth: 260 }}>OCR: {unit.raw_text}</div>}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button disabled={saving === unit.id} onClick={() => review(unit, "confirm")} style={{ marginInlineEnd: ".4rem" }}>
                        {saving === unit.id ? "שומר…" : verified ? "שמור תיקון" : "אשר"}
                      </button>
                      <button disabled={saving === unit.id} onClick={() => review(unit, "reject")} style={{ background: "#7a342b" }}>דחה</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
