"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getCandidates,
  searchCandidates,
  type Assessment,
  type Candidate,
} from "@/lib/api";
// מ-`lib` ולא מהקומפוננטה: ייבוא מ-`DrawPolygon` גורר את leaflet
// לחבילת ה-SSR, שם אין `window`, והדף מחזיר 500 בטעינה נקייה.
import { MAX_AREA_SQM } from "@/lib/searchArea";

const STATUS_LABEL: Record<Assessment["status"], string> = {
  eligible: "כשיר",
  needs_verification: "דורש אימות",
  urban_renewal_compound: "מסלול מתחמים",
  ineligible: "אינו כשיר",
};

const STATUS_COLOUR: Record<Assessment["status"], string> = {
  eligible: "#1f5f55",
  needs_verification: "#8a6100",
  urban_renewal_compound: "#1d4e89",
  ineligible: "#a8321e",
};

/** Gate ids come from the rules engine in English. A developer reading the screen
 *  should see what is missing, not a field name. */
const GATE_LABEL: Record<string, string> = {
  residential_zoning: "ייעוד למגורים",
  residential_share: "70% שימוש למגורים",
  permit_date: "מועד ההיתר",
  strengthened: "בוצע חיזוק",
  occupied: "יוזמה פעילה של אחר",
  floors: "מספר קומות",
  units: "מספר דירות",
  scope_buildings: "מספר מבנים",
  renewal_policy_category: "קטגוריה במפת המדיניות",
  street_width: "רוחב רחוב",
};

const gateText = (ids: string[]) => ids.map((id) => GATE_LABEL[id] ?? id).join(", ");

/** The floor figure as it may honestly be written: a number only when the whole
 *  tolerance band agrees, a range when it does not, and never a number at all
 *  when the street width was not measured. */
function floorsText(a: Assessment | null): string {
  if (!a || a.floors_low === null) return "—";
  const base = a.floors_high !== null && a.floors_high !== a.floors_low
    ? `${a.floors_low}–${a.floors_high}`
    : String(a.floors_low);
  if (a.case_by_case) return `${base} · נקודתית`;
  return a.floors_certain ? base : `${base} · דורש מדידה`;
}

const dunam = (sqm: number) => `${(sqm / 1000).toFixed(1)} דונם`;

const OpportunityMap = dynamic(() => import("@/components/Map"), { ssr: false });

const DEFAULT_CITY = "herzliya";

export default function DashboardPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [drawing, setDrawing] = useState(false);
  const [searchArea, setSearchArea] = useState<object | null>(null);
  const [liveArea, setLiveArea] = useState<{ points: number; sqm: number } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError(null);
    getCandidates(DEFAULT_CITY)
      .then(setCandidates)
      .catch((e) => setError(e instanceof ApiError ? e.detail : "לא ניתן לטעון מועמדים. האם השרת רץ?"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(loadAll, [loadAll]);

  function onPolygon(polygon: object, areaSqm: number) {
    setDrawing(false);
    setLiveArea(null);
    setSearchArea(polygon);
    setSelectedId(null);
    setLoading(true);
    setError(null);
    searchCandidates(DEFAULT_CITY, polygon)
      .then(setCandidates)
      // ‏422 כאן אינו תקלה אלא MAP-01 עושה את עבודתו, והמשפט בעברית הוא
      // מה שהמשתמש צריך לפעול לפיו — ולכן הוא מוצג כמו שהוא.
      .catch((e) => {
        setError(e instanceof ApiError ? e.detail : "החיפוש נכשל.");
        setCandidates([]);
      })
      .finally(() => setLoading(false));
  }

  function clearArea() {
    setSearchArea(null);
    setSelectedId(null);
    loadAll();
  }

  const overLimit = liveArea !== null && liveArea.points >= 3 && liveArea.sqm > MAX_AREA_SQM;

  return (
    <main className="page" style={{ maxWidth: 1100 }}>
      <h1>מועמדים · הרצליה</h1>

      <div className="card" style={{ marginBottom: "1rem", padding: "0.9rem 1.1rem" }}>
        <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap" }}>
          {!drawing ? (
            <button onClick={() => { setDrawing(true); setLiveArea(null); }}>
              ✏️ צייר אזור חיפוש
            </button>
          ) : (
            <button onClick={() => { setDrawing(false); setLiveArea(null); }} style={{ background: "#6b655c" }}>
              בטל ציור
            </button>
          )}

          {searchArea && !drawing && (
            <button onClick={clearArea} style={{ background: "#6b655c" }}>
              נקה אזור · הצג הכל
            </button>
          )}

          <span style={{ color: "#6b655c", fontSize: ".88rem" }}>
            {drawing
              ? liveArea === null
                ? "לחיצה מוסיפה קודקוד · לחיצה כפולה או Enter לסיום · Escape לביטול"
                : `${liveArea.points} קודקודים · ${dunam(liveArea.sqm)}`
              : searchArea
                ? "התוצאות מוגבלות לאזור המסומן על המפה"
                : "מוצגים כל המועמדים בעיר"}
          </span>

          {overLimit && (
            <span style={{ color: "#a8321e", fontWeight: 600, fontSize: ".88rem" }}>
              מעל מגבלת {MAX_AREA_SQM / 1000} הדונם — השרת ידחה
            </span>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1.2rem", padding: 0, overflow: "hidden" }}>
        <OpportunityMap
          candidates={candidates}
          drawing={drawing}
          searchArea={searchArea}
          onPolygon={onPolygon}
          onCancelDraw={() => { setDrawing(false); setLiveArea(null); }}
          onDrawProgress={(points, sqm) => setLiveArea({ points, sqm })}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>

      {error && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "#e6c9c2", background: "#fdf6f4" }}>
          <strong style={{ color: "#a8321e" }}>{error}</strong>
        </div>
      )}

      <div className="card">
        <p style={{ margin: "0 0 .8rem", color: "#6b655c", fontSize: ".9rem" }}>
          {loading ? "טוען…" : `${candidates.length} מועמדים`}
        </p>
        <table>
          <thead>
            <tr>
              <th>כתובת</th>
              <th>גוש / חלקה</th>
              <th>שטח (מ״ר)</th>
              <th>קומות</th>
              <th>מצב</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => (
              <tr
                key={candidate.id}
                onClick={() => setSelectedId(candidate.id)}
                style={{
                  cursor: "pointer",
                  background: candidate.id === selectedId ? "#fdf3e8" : undefined,
                }}
              >
                <td>{candidate.address}</td>
                <td>
                  {candidate.block ?? "—"} / {candidate.parcel ?? "—"}
                </td>
                <td>{candidate.area_sqm ?? "—"}</td>
                <td>{floorsText(candidate.assessment)}</td>
                <td>
                  {candidate.assessment ? (
                    <span style={{ color: STATUS_COLOUR[candidate.assessment.status], fontWeight: 600 }}>
                      {STATUS_LABEL[candidate.assessment.status]}
                      {candidate.assessment.blocking.length > 0 && (
                        <span style={{ color: "#6b655c", fontWeight: 400 }}>
                          {" "}· ממתין ל{gateText(candidate.assessment.blocking)}
                        </span>
                      )}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
            {!loading && candidates.length === 0 && !error && (
              <tr>
                <td colSpan={5} style={{ color: "#6b655c" }}>
                  אין מועמדים באזור שסומן.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
