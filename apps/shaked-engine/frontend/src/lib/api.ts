const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("shaked_token");
}

export function setToken(token: string): void {
  window.localStorage.setItem("shaked_token", token);
}

export function clearToken(): void {
  window.localStorage.removeItem("shaked_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API request failed (${response.status}): ${body}`);
  }
  return response.json() as Promise<T>;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/jwt/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new Error("Login failed");
  }
  return response.json() as Promise<LoginResponse>;
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: number[][][][]; // GeoJSON order: [lng, lat] per position
}

/**
 * What the rights chain concluded about one candidate.
 *
 * `status` is what a user needs to see, not `verification_level`:
 * verification_level describes how a fact was obtained (raw, ocr, ai, human)
 * and is correctly "raw" for every candidate, since ours are read from
 * official GIS layers with no OCR and no human check. Shown to a user it
 * reads as "nothing has been checked", which is the opposite of the truth.
 */
export interface Assessment {
  status: "eligible" | "needs_verification" | "urban_renewal_compound" | "ineligible";
  floors_low: number | null;
  floors_high: number | null;
  /** the whole tolerance band gives the same answer */
  floors_certain: boolean;
  /** over 15 m the street stops binding; the category ceiling governs, subject to review */
  case_by_case: boolean;
  cap_400_sqm: number | null;
  /** "estimate" means the input rests on an assumption and cannot decide a gate */
  cap_400_certainty: string | null;
  /** gate ids that are failing, unknown or routed */
  blocking: string[];
  deliverable: boolean;
}

export interface Candidate {
  id: string;
  address: string;
  block: string | null;
  parcel: string | null;
  xplan_code: string | null;
  area_sqm: number | null;
  verification_level: string;
  category: string | null;
  geometry: MultiPolygonGeometry | null;
  centroid: { lat: number; lng: number } | null;
  assessment: Assessment | null;
}

export function getCandidates(
  cityCode: string,
  options: { deliverableOnly?: boolean; limit?: number } = {},
): Promise<Candidate[]> {
  const query = new URLSearchParams();
  if (options.deliverableOnly) query.set("deliverable_only", "true");
  if (options.limit) query.set("limit", String(options.limit));
  const suffix = query.toString() ? `?${query}` : "";
  return request<Candidate[]>(`/api/v1/candidates/${cityCode}${suffix}`);
}

/** Candidates inside a drawn area. A polygon that is invalid, too large or
 *  outside the city comes back as 422 with a Hebrew message meant for the user. */
export function searchCandidates(
  cityCode: string,
  polygon: object,
  options: { deliverableOnly?: boolean; minAreaSqm?: number; limit?: number } = {},
): Promise<Candidate[]> {
  return request<Candidate[]>(`/api/v1/candidates/${cityCode}/search`, {
    method: "POST",
    body: JSON.stringify({
      polygon,
      deliverable_only: options.deliverableOnly ?? false,
      min_area_sqm: options.minAreaSqm,
      limit: options.limit ?? 100,
    }),
  });
}
