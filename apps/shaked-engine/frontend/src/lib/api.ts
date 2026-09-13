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

/**
 * An API refusal, with the message the server meant a person to read.
 *
 * The refusals here are not plumbing errors: "כל אזור החיפוש חייב להיות
 * בתוך הגבול העירוני הרשמי" and "מגבלת האזור היא 250 דונם" are MAP-01
 * doing its job, and the user is the one who has to act on them. Throwing
 * `API request failed (422): {"detail":"..."}` buries the sentence inside
 * a stringified body, so nothing could show it.
 */
export class ApiError extends Error {
  readonly status: number;
  /** the Hebrew sentence, when the server sent one */
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const FALLBACK: Record<number, string> = {
  401: "נדרשת התחברות מחדש.",
  402: "לא נותרה זכאות לחברה.",
  404: "לא נמצא.",
  409: "המועמד אינו מוכן למסירה.",
  422: "הבקשה אינה תקינה.",
};

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
    let detail = FALLBACK[response.status] ?? `השרת החזיר ${response.status}.`;
    try {
      const body = await response.json();
      // FastAPI puts a string in `detail` for HTTPException, and a list of
      // field errors there for a validation failure. Only the first is meant
      // for a person.
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* לא JSON — נשארים עם המשפט הכללי */
    }
    throw new ApiError(response.status, detail);
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
  /** §70א gates that were never answered — distinct from gates that failed */
  threshold_open?: string[];
  /**
   * Two different questions, and they were one flag until they were split.
   *
   * `screenable` — still in the running: has a floor figure, not rejected,
   * not routed to the compound track. This is what the screen lists.
   *
   * `deliverable` — the §70א threshold was actually ASKED and answered.
   * False while the building file has not been pulled, which is most of
   * the inventory: the archive is fetched per customer request, and the
   * moment of delivery is the moment it happens.
   */
  screenable?: boolean;
  deliverable: boolean;
}

export interface Candidate {
  id: string;
  address: string;
  block: string | null;
  parcel: string | null;
  area_sqm: number | null;
  verification_level: string;
  category: string | null;
  geometry: MultiPolygonGeometry | null;
  centroid: { lat: number; lng: number } | null;
  assessment: Assessment | null;
  /** ההעדפה שהכריעה את מקומו מול הבא אחריו — SEL-01 דורש נימוק לכל בחירה */
  why_selected?: string;
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

/** שדה שאפשר למיין לפיו. הרשימה נאכפת גם בשרת — ‏422 על שם שאינו כאן. */
export type SortField = "parcel_area" | "units" | "floors" | "cap_400";

export interface Preference {
  field: SortField;
  direction: "asc" | "desc";
}

/**
 * תנאי חובה וסדר העדפות — **שני דברים, לא אחד**.
 *
 * ה-PRD מפריד ביניהם (SEL-01: ״כללים, תנאי חובה וסדר העדיפויות״): תנאי
 * חובה מוציא מועמד מהרשימה, והעדפה רק מזיזה אותו בה. מינימום שנשלח
 * כהעדפה היה מדרג נמוך מועמד שהיזם כלל אינו רוצה לראות.
 */
export interface SearchOptions {
  // ── תנאי חובה ──
  minAreaSqm?: number;
  minUnits?: number;
  minFloors?: number;
  minCap400Sqm?: number;
  certainFloorsOnly?: boolean;
  deliverableOnly?: boolean;
  // ── סדר העדפות, עד שלוש ──
  preferences?: Preference[];
  limit?: number;
}

/** Candidates inside a drawn area. A polygon that is invalid, too large or
 *  outside the city comes back as 422 with a Hebrew message meant for the user. */
export function searchCandidates(
  cityCode: string,
  polygon: object,
  options: SearchOptions = {},
): Promise<Candidate[]> {
  return request<Candidate[]>(`/api/v1/candidates/${cityCode}/search`, {
    method: "POST",
    body: JSON.stringify({
      polygon,
      min_area_sqm: options.minAreaSqm,
      min_units: options.minUnits,
      min_floors: options.minFloors,
      min_cap_400_sqm: options.minCap400Sqm,
      certain_floors_only: options.certainFloorsOnly ?? false,
      deliverable_only: options.deliverableOnly ?? false,
      preferences: options.preferences ?? [],
      limit: options.limit ?? 100,
    }),
  });
}


// ── מסירות, יתרה וחבילות ──

export interface DeliveredOpportunity {
  delivery_id: string;
  opportunity_id: string;
  address: string;
  block: string | null;
  parcel: string | null;
  delivered_at: string | null;
  credits_charged: number;
  rules_version: string;
  data_version: string;
  why_selected: Record<string, unknown> | null;
  assessment: Assessment | null;
}

/** מה שכבר נמסר לחברה — SEL-02: "מוצג במאגר החברה בלבד". */
export function getMyDeliveries(cityCode: string): Promise<DeliveredOpportunity[]> {
  return request<DeliveredOpportunity[]>(`/api/v1/candidates/${cityCode}/mine`);
}

/**
 * מוסר הזדמנות לחברה ומנכה זכאות.
 *
 * מועמד שתנאי הסף שלו לא נשאל — תיק הבניין נשלף בתוך הבקשה הזו ואז
 * המסירה מנוסה שוב, ולכן היא עשויה לקחת כמה שניות. ‏409 פירושו שגם אחרי
 * השליפה השער נשאר פתוח; ‏402 פירושו שאין יתרה.
 */
export function deliverOpportunity(
  cityCode: string,
  opportunityId: string,
): Promise<{ delivery_id: string; opportunity_id: string; charged: boolean; delivered_at: string }> {
  return request(`/api/v1/candidates/${cityCode}/${opportunityId}/deliver`, { method: "POST" });
}

export interface AccountBalance {
  credits_remaining: number;
  delivered_count: number;
  company_id: string;
  updated_at: string | null;
}

export function getBalance(): Promise<AccountBalance> {
  return request<AccountBalance>("/api/v1/account/balance");
}

export interface CreditPackage {
  id: string;
  name: string;
  credits: number;
  price_ils: number;
}

export function getPackages(): Promise<CreditPackage[]> {
  return request<CreditPackage[]>("/api/v1/account/packages");
}

export function purchasePackage(packageId: string): Promise<{
  package: string;
  credits_added: number;
  credits_remaining: number;
}> {
  return request(`/api/v1/account/packages/${packageId}/purchase`, { method: "POST" });
}
