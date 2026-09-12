"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { getCandidates, type Candidate } from "@/lib/api";

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
              <th>Verification</th>
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
                <td>{candidate.verification_level}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
