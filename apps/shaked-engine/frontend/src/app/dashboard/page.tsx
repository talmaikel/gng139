"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { getCandidates, type Assessment, type Candidate } from "@/lib/api";

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

const OpportunityMap = dynamic(() => import("@/components/Map"), { ssr: false });

const DEFAULT_CITY = "herzliya";

export default function DashboardPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCandidates(DEFAULT_CITY)
      .then(setCandidates)
      .catch(() => setError("Could not load candidates. Are you signed in and is the API running?"));
  }, []);

  return (
    <main className="page">
      <h1>Candidate opportunities — Herzliya</h1>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <OpportunityMap candidates={candidates} />
      </div>

      {error && <p style={{ color: "#b3261e" }}>{error}</p>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Address</th>
              <th>Block / Parcel</th>
              <th>Area (sqm)</th>
              <th>Category</th>
              <th>קומות</th>
              <th>מצב</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => (
              <tr key={candidate.id}>
                <td>{candidate.address}</td>
                <td>
                  {candidate.block ?? "—"} / {candidate.parcel ?? "—"}
                </td>
                <td>{candidate.area_sqm ?? "—"}</td>
                <td>{candidate.category ?? "—"}</td>
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
          </tbody>
        </table>
      </div>
    </main>
  );
}
