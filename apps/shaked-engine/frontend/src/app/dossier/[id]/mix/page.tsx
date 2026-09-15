"use client";

import Link from "next/link";
import { use, useState } from "react";

interface Candidate {
  counts: Record<string, number>;
  total_new_units: number;
  developer_units: number;
  tenant_units: number;
  tenant_allocation_sqm: number;
  developer_used_sqm: number;
  developer_available_sqm: number;
  unused_developer_sqm: number;
  gross_developer_revenue_ils: number;
  projected_profit_ils: number;
  profit_margin_on_cost_ratio: number;
  meets_developer_target: boolean;
}

interface OptimizationResponse {
  address: string;
  planned_unit_mix: { rooms: number; area_sqm: number; units: number }[];
  planned_unit_mix_meta: {
    status: string;
    compensation_sqm_per_existing_unit: number;
    compensation_source: string;
    default_compensation_source: string | null;
    projected_profit_ils: number;
    profit_margin_on_cost_ratio: number;
    market_comparable_count: number;
    market_as_of_date: string;
    unit_area_assumption_source: string;
    warnings: string[];
  };
  optimization: {
    feasible: boolean;
    compensation_sqm_per_existing_unit: number;
    compensation_source: string;
    tenant_allocation_sqm: number;
    developer_available_sqm: number;
    candidates: Candidate[];
    warnings: string[];
  };
}

const ils = (value: number) => `${Math.round(value).toLocaleString("he-IL")} ₪`;
const sqm = (value: number) => `${Math.round(value).toLocaleString("he-IL")} מ״ר`;

export default function UnitMixPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [compensation, setCompensation] = useState("");
  const [result, setResult] = useState<OptimizationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function optimize() {
    setBusy(true);
    setError(null);
    try {
      const token = window.localStorage.getItem("shaked_token");
      const parsed = compensation.trim() === "" ? null : Number(compensation);
      if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) {
        setError("יש להזין תוספת שטח תקינה, או להשאיר ריק לברירת המחדל.");
        return;
      }
      const response = await fetch(`/api/v1/unit-mix/${id}/optimize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          compensation_sqm_per_existing_unit: parsed,
          persist: true,
        }),
      });
      if (!response.ok) {
        let message = "לא ניתן לחשב תמהיל כרגע.";
        try {
          const body = await response.json();
          if (typeof body?.detail === "string") message = body.detail;
        } catch { /* keep fallback */ }
        throw new Error(message);
      }
      setResult((await response.json()) as OptimizationResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "לא ניתן לחשב תמהיל כרגע.");
    } finally {
      setBusy(false);
    }
  }

  const best = result?.optimization.candidates[0];

  return (
    <main className="page" style={{ maxWidth: 1000 }}>
      <p style={{ margin: "0 0 .6rem" }}>
        <Link href={`/dossier/${id}`} style={{ color: "#6b655c", fontSize: ".85rem" }}>
          ← חזרה לתיק
        </Link>
      </p>

      <h1 style={{ marginBottom: ".25rem" }}>תמהיל דירות ורווחיות</h1>
      <p style={{ marginTop: 0, color: "#6b655c" }}>
        הזן את התמורה לבעלי הדירות. שינוי התמורה מחשב מחדש את השטח ליזם, התמהיל והרווח.
        אם השדה נשאר ריק, המערכת משתמשת בתמורת ברירת המחדל המסומנת כאומדן.
      </p>

      <section className="card" style={{ marginBottom: "1rem" }}>
        <label htmlFor="compensation" style={{ display: "block", fontWeight: 700, marginBottom: ".35rem" }}>
          תוספת מ״ר לכל דירה קיימת
        </label>
        <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center" }}>
          <input
            id="compensation"
            type="number"
            min="0"
            max="100"
            step="1"
            value={compensation}
            onChange={(e) => setCompensation(e.target.value)}
            placeholder="ברירת מחדל מהשוק"
            style={{ maxWidth: 220 }}
          />
          <button onClick={optimize} disabled={busy} style={{ background: "#1d4e89" }}>
            {busy ? "מחשב…" : "חשב תמהיל מיטבי"}
          </button>
        </div>
        <p style={{ color: "#6b655c", fontSize: ".82rem", marginBottom: 0 }}>
          החישוב משתמש בלוח הדירות המאומת, בזכויות שכבר חושבו, בעסקאות ההשוואה השמורות ובמודל דוח 0 הקיים.
        </p>
      </section>

      {error && (
        <section className="card" style={{ marginBottom: "1rem", background: "#fdf6f4", borderColor: "#e6c9c2" }}>
          <strong style={{ color: "#a8321e" }}>{error}</strong>
          {error.includes("לוח דירות") && (
            <p style={{ marginBottom: 0 }}>
              <Link href={`/dossier/${id}/units`}>פתח את מסך אישור הדירות הקיימות ←</Link>
            </p>
          )}
        </section>
      )}

      {result && best && (
        <>
          <section className="card" style={{ marginBottom: "1rem" }}>
            <h2 style={{ marginTop: 0 }}>התמהיל המומלץ</h2>
            <p style={{ marginTop: 0, color: "#6b655c" }}>{result.address}</p>
            <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <div><small>תמורה שנלקחה בחשבון</small><br/><strong>{sqm(result.optimization.compensation_sqm_per_existing_unit)}</strong></div>
              <div><small>שטח דירות בעלים</small><br/><strong>{sqm(result.optimization.tenant_allocation_sqm)}</strong></div>
              <div><small>שטח זמין ליזם</small><br/><strong>{sqm(result.optimization.developer_available_sqm)}</strong></div>
              <div><small>רווח צפוי</small><br/><strong>{ils(best.projected_profit_ils)}</strong></div>
              <div><small>רווח על העלות</small><br/><strong>{(best.profit_margin_on_cost_ratio * 100).toFixed(1)}%</strong></div>
            </div>

            <table>
              <thead><tr><th>חדרים</th><th>שטח לדירה</th><th>מספר דירות יזם</th></tr></thead>
              <tbody>
                {result.planned_unit_mix.map((row) => (
                  <tr key={`${row.rooms}-${row.area_sqm}`}>
                    <td>{row.rooms}</td><td>{sqm(row.area_sqm)}</td><td>{row.units}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ color: "#6b655c", fontSize: ".82rem" }}>
              {result.planned_unit_mix_meta.market_comparable_count} עסקאות השוואה · נכון ל-{result.planned_unit_mix_meta.market_as_of_date} ·
              התמהיל נשמר כאומדן ולא כזכות מאושרת.
            </p>
          </section>

          {result.optimization.candidates.length > 1 && (
            <section className="card" style={{ marginBottom: "1rem" }}>
              <h2 style={{ marginTop: 0 }}>חלופות מובילות</h2>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th>#</th><th>תמהיל</th><th>דירות יזם</th><th>רווח</th><th>רווח על העלות</th><th>שטח לא מנוצל</th></tr></thead>
                  <tbody>
                    {result.optimization.candidates.slice(0, 5).map((candidate, index) => (
                      <tr key={index}>
                        <td>{index + 1}</td>
                        <td>{Object.entries(candidate.counts).map(([k, v]) => `${k}: ${v}`).join(" · ")}</td>
                        <td>{candidate.developer_units}</td>
                        <td>{ils(candidate.projected_profit_ils)}</td>
                        <td>{(candidate.profit_margin_on_cost_ratio * 100).toFixed(1)}%</td>
                        <td>{sqm(candidate.unused_developer_sqm)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="card">
            <h2 style={{ marginTop: 0 }}>מה חשוב לדעת</h2>
            <ul style={{ marginBottom: 0 }}>
              <li>ברירת המחדל לתמורה: {result.planned_unit_mix_meta.default_compensation_source ?? "אומדן גרסה"}.</li>
              <li>שטחי 3/4/5 חדרים הם הנחות מודל מסומנות, לא הוראה של עיריית הרצליה.</li>
              {result.optimization.warnings.map((warning, i) => <li key={i}>{warning}</li>)}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
