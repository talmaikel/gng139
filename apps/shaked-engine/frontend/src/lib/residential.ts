// ‏W10 · #115 · יחס המגורים של §70א, מוזן מטבלת השטחים בגרמושקה.
// הקריאה לשרת כאן ולא ב-api.ts, באותו דפוס של אסימון ושגיאה.
import { ApiError } from "./api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// ‏§70א: ״70% לפחות משטח הבנייה הכולל הקיים שלו משמש כדין למגורים״.
export const RESIDENTIAL_SHARE_MIN = 0.7;

export interface ShareGate {
  id: string;
  label: string;
  status: string;
  source_url: string;
  page: number | null;
  detail: string | null;
}

export interface ResidentialShareEntry {
  residential_share: number;
  source_url: string | null;
  retrieved_at: string | null;
  location: string | null;
  method: string | null;
}

export interface ResidentialShareState {
  opportunity_id: string;
  address: string;
  /** מה שהשער מכריע לפיו בפועל — null כשאין, כשהתיישן או כשיש סתירה */
  residential_share: number | null;
  certainty: string | null;
  stale: boolean;
  /** ההזנה הידנית האחרונה, גם אם אינה מכריעה עוד */
  entry: ResidentialShareEntry | null;
  gate: ShareGate;
  assessment: { status: string | null; deliverable: boolean | null };
}

export interface ResidentialShareInput {
  residential_sqm: number;
  total_sqm: number;
  source_url: string;
  page: string | null;
  note: string | null;
}

/** היחס כפי שיישמר: ארבע ספרות, כמו בשרת. */
export const shareOf = (residentialSqm: number, totalSqm: number) =>
  Math.round((residentialSqm / totalSqm) * 1e4) / 1e4;

/** כמו השרת: 69.96% שנכשל אינו מוצג ״70%״. */
export function sharePct(share: number): string {
  const shown = Math.round(share * 100);
  if (share < RESIDENTIAL_SHARE_MIN && shown >= RESIDENTIAL_SHARE_MIN * 100) {
    return `${(Math.floor(Math.round(share * 1e6) / 1e3) / 10).toFixed(1)}%`;
  }
  return `${shown}%`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window === "undefined" ? null : window.localStorage.getItem("shaked_token");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = response.status === 404 ? "התיק אינו במאגר החברה."
      : response.status === 422 ? "הערכים אינם תקינים."
      : `השרת החזיר ${response.status}.`;
    if (response.status !== 401) {
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
        // שגיאת אימות של שדה: רק הודעה שנכתבה בעברית מיועדת לאדם
        const msg = Array.isArray(body?.detail) ? String(body.detail[0]?.msg ?? "") : "";
        if (/[א-ת]/.test(msg)) detail = msg.replace(/^Value error, /, "");
      } catch {
        /* לא JSON */
      }
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const getResidentialShare = (opportunityId: string) =>
  request<ResidentialShareState>(`/api/v1/dossiers/${opportunityId}/residential-share`);

export const saveResidentialShare = (opportunityId: string, input: ResidentialShareInput) =>
  request<ResidentialShareState>(`/api/v1/dossiers/${opportunityId}/residential-share`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
