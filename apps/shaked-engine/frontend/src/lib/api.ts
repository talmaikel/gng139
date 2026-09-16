// ריק = אותו מקור. ‏Next מעביר את `/api/*` לשרת (ראה `next.config.js`),
// ולכן האפליקציה עובדת גם ממחשב אחר, מטלפון, ומאחורי מנהרה — ובלי CORS.
// ‏`NEXT_PUBLIC_API_BASE_URL` נשאר כמוצא אחרון לפריסה שמפרידה את השניים.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

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
  403: "אין הרשאה לפעולה הזו.",
  404: "לא נמצא.",
  409: "המועמד אינו מוכן למסירה.",
  422: "הבקשה אינה תקינה.",
  503: "שירות חיצוני אינו זמין כרגע. אפשר לנסות שוב בעוד כמה דקות.",
};

/** האם כדאי לנסות שוב. ‏503 הוא ״נסה שוב״; ‏409 הוא ״לא המועמד הזה״,
 *  ולהציג אותם אותו דבר פירושו לקוח שמוותר על מועמד תקין. */
export const isRetryable = (e: unknown) => e instanceof ApiError && e.status === 503;

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
    // ‏401 מגיע מ-FastAPI-Users כ-"Unauthorized" — מילה שנכתבה למפתח, לא
    // למשתמש, והיא הופיעה על המסך כמו שהיא. שם ההודעה שלנו מנצחת תמיד.
    if (response.status !== 401) {
      try {
        const body = await response.json();
        // FastAPI puts a string in `detail` for HTTPException, and a list of
        // field errors there for a validation failure. Only the first is meant
        // for a person.
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* לא JSON — נשארים עם המשפט הכללי */
      }
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
    let detail = "Login failed";
    if (response.status === 429) {
      try {
        detail = (await response.json())?.detail ?? detail;
      } catch {
        /* לא JSON */
      }
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<LoginResponse>;
}

export interface SignupInput {
  company_name: string;
  full_name: string;
  email: string;
  password: string;
}

/** לקוח חדש: חברה חדשה והנרשם כ-owner שלה. מחזיר טוקן — הנרשם כבר מחובר.
 *  ‏409 = המייל תפוס, ‏422 = סיסמה או שדה שנדחו, עם משפט בעברית. */
export function signup(input: SignupInput): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// ── שחזור סיסמה ואימות מייל (FastAPI-Users) ──
//
// השגיאות שם מגיעות כקוד ולא כמשפט: ‏"RESET_PASSWORD_BAD_TOKEN", או
// ‏{code, reason} כשהסיסמה נדחתה. בלי המיפוי הזה המסך היה מציג את הקוד.

const AUTH_CODES: Record<string, string> = {
  RESET_PASSWORD_BAD_TOKEN: "הקישור אינו תקף או שכבר נוצל. אפשר לבקש קישור חדש.",
  VERIFY_USER_BAD_TOKEN: "קישור האימות אינו תקף או שפג תוקפו.",
  VERIFY_USER_ALREADY_VERIFIED: "כתובת המייל כבר מאומתת.",
};

async function authPost(path: string, body: object): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.ok) return;
  let detail = FALLBACK[response.status] ?? `השרת החזיר ${response.status}.`;
  try {
    const data = await response.json();
    const d = data?.detail;
    if (typeof d === "string") detail = AUTH_CODES[d] ?? d;
    else if (d && typeof d.reason === "string") detail = d.reason;
  } catch {
    /* לא JSON */
  }
  throw new ApiError(response.status, detail);
}

/** תמיד מצליח למייל קיים ולא-קיים — השרת אינו מגלה מי רשום. */
export const forgotPassword = (email: string) => authPost("forgot-password", { email });
export const resetPassword = (token: string, password: string) =>
  authPost("reset-password", { token, password });
export const requestVerification = (email: string) => authPost("request-verify-token", { email });
export const verifyEmail = (token: string) => authPost("verify", { token });

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
  /** ‏S1 · המפה של הלקוח מציגה רק את מה שנמסר לו */
  geometry?: MultiPolygonGeometry | null;
  centroid?: { lat: number; lng: number } | null;
}

// ── S1/S2 · סריקה: פוליגון → עד שלושה תיקים, בלי לחשוף מועמדים ──

/** מספרים בלבד, לפני החיוב. */
export interface ScanPreview {
  found: number;
  offer: number;
  ready: number;
  needs_fetch: number;
  credits_remaining: number;
}

export interface ScanResult {
  delivered: DeliveredOpportunity[];
  /** כמה מועמדים היו באזור. 0 = אין הזדמנויות כאן. */
  found: number;
  requested: number;
  skipped: number;
  retryable: boolean;
  message: string | null;
  credits_remaining: number;
}

function scanBody(polygon: object, options: SearchOptions, readyOnly = false): string {
  return JSON.stringify({
    polygon,
    ready_only: readyOnly,
    min_area_sqm: options.minAreaSqm,
    min_units: options.minUnits,
    min_floors: options.minFloors,
    min_cap_400_sqm: options.minCap400Sqm,
    certain_floors_only: options.certainFloorsOnly ?? false,
    preferences: options.preferences ?? [],
  });
}

export function previewScan(cityCode: string, polygon: object, options: SearchOptions = {}): Promise<ScanPreview> {
  return request<ScanPreview>(`/api/v1/candidates/${cityCode}/scan/preview`, {
    method: "POST", body: scanBody(polygon, options),
  });
}

/** מוסר עד שלושה תיקים מהאזור. עם `readyOnly` — רק תיקים שלמים, מיד, בלי
 *  שליפה מהארכיון; בלעדיו עשוי לקחת עד כדקה. */
export function runScan(cityCode: string, polygon: object, options: SearchOptions = {}, readyOnly = false): Promise<ScanResult> {
  return request<ScanResult>(`/api/v1/candidates/${cityCode}/scan/deliver`, {
    method: "POST", body: scanBody(polygon, options, readyOnly),
  });
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

export type PaymentMethod = "card" | "bit" | "paypal";

/** ‏**תשלום מדומה** (טל, 16.09): מוסיף את זכאות החבילה מיד, בלי סליקה.
 *  פעיל רק כשהשרת רץ עם `SIMULATED_PAYMENTS=true`; אחרת 404, והחלון חוזר
 *  לפרטי הקשר. כשתחובר סליקה אמיתית — היא נכנסת כאן. */
export function purchasePackage(packageId: string, method: PaymentMethod):
  Promise<{ package: string; credits_added: number; credits_remaining: number }> {
  return request(`/api/v1/account/packages/${packageId}/purchase`, {
    method: "POST", body: JSON.stringify({ method }),
  });
}


// ── אדמין: זכאות ידנית בפיילוט ──

export interface Me {
  id: string;
  email: string;
  full_name: string;
  role: string;
  company_id: string;
  is_superuser: boolean;
  is_verified: boolean;
}

export function getMe(): Promise<Me> {
  return request<Me>("/api/v1/auth/users/me");
}

export interface AdminCompany {
  id: string;
  name: string;
  emails: string[];
  credits_remaining: number;
  created_at: string | null;
}

export interface CreditGrantRow {
  credits: number;
  note: string;
  granted_by: string | null;
  created_at: string | null;
}

export function adminFindCompanies(q: string): Promise<AdminCompany[]> {
  return request<AdminCompany[]>(`/api/v1/admin/companies?q=${encodeURIComponent(q)}`);
}

/** ‏`note` הוא האסמכתה — מספר חשבונית או תשלום. השרת מסרב בלעדיה. */
export function adminGrantCredits(
  companyId: string,
  grant: { package_id?: string; credits?: number; note: string },
): Promise<{ company: string; credits_added: number; credits_remaining: number }> {
  return request(`/api/v1/admin/companies/${companyId}/credits`, {
    method: "POST",
    body: JSON.stringify(grant),
  });
}

export function adminGrantHistory(companyId: string): Promise<CreditGrantRow[]> {
  return request<CreditGrantRow[]>(`/api/v1/admin/companies/${companyId}/credits`);
}


// ── התיק ──

export interface Gate {
  id: string;
  label: string;
  /** passed · failed · unknown · routed · undefined · needs_measurement */
  status: string;
  source_url: string;
  page: number | null;
  detail: string | null;
}

export interface EvidenceRow {
  field: string;
  /** התווית בעברית — מגיעה מהשרת, כדי שה-PDF, ה-Excel והמסך יאמרו אותו דבר */
  label?: string;
  value: unknown;
  certainty: string;
  certainty_label?: string;
  /** האם התצפית רשאית להכריע שער — ודאות, מקור, מיקום וגיל, כולם יחד */
  decides: boolean;
  /** המונח שמסביר את השדה, כשהתווית לבדה אינה מספיקה. */
  term?: TermId | null;
  source_url: string | null;
  retrieved_at: string | null;
  location: string | null;
  method: string | null;
}

/** ‏W4 · מונח אחד מהמילון שבשרת (`glossary.py`). אותו נוסח במסך, ב-PDF ובאקסל. */
export interface GlossaryEntry {
  term: string;
  short: string;
  source_url?: string | null;
}

/** המונחים שהמסך מציג ליד תוויות. **`tests/test_glossary.py` קורא את הרשימה
 *  הזו** ונופל כשמזהה כאן אינו במילון בשרת — ״?״ שנפתח ריק הוא באג שקט. */
export const TERM_IDS = [
  "shaked_conditions", "routed", "needs_measurement", "policy_silent", "certain_floors",
  "category_floors", "residential_share", "cap_400", "post_2005",
  "deciding", "certainty",
  "profit_on_cost", "developer_area",
  "levy_ceiling", "breakeven_land_value", "levy_estimate", "levy_category",
] as const;
export type TermId = (typeof TERM_IDS)[number];

export interface Dossier {
  identity: {
    opportunity_id: string;
    address: string;
    block: string | null;
    parcel: string | null;
    city_code: string;
    area_sqm: number | null;
    existing_units: number | null;
  };
  rights: {
    checks: Gate[];
    status: Assessment["status"];
    floors: { low: number | null; high: number | null; certain: boolean; case_by_case: boolean };
    cap_400_sqm: number | null;
    cap_400_basis: string | null;
    cap_400_certainty: string | null;
    cap_400_reliable?: boolean;
    unit_mix?: Record<string, number>;
    parking?: Record<string, unknown>;
    balconies_sqm?: number;
    balconies_why?: string;
    allocation_sqm?: number | null;
    allocation_why?: string;
    notes: string[];
    stale_fields: string[];
  };
  evidence: EvidenceRow[];
  economics: {
    scenario: Record<string, number | boolean | string[]> | null;
    assumptions: Record<string, {
      value: number; status: string; unit: string; source: string | null; label: string;
    }>;
    assumptions_version: string;
    assumptions_effective_date: string;
    inputs_missing: string[];
    /** המשפט שהיזם קורא כשאין תרחיש — מחובר בשרת, לא כאן. */
    not_delivered_reason: string | null;
    is_deliverable: boolean;
    disclaimer: string;
    /** על מה הרווח נשען ואינו ודאי, בסדר ההשפעה. משפטים מוכנים מהשרת (B8). */
    caveats: { id: string; text: string }[];
    /** ‏E1 · מעל או מתחת לרווח היזמי המזערי (16%). משפט מהשרת. */
    profit_verdict?: string;
    /** ‏B15 · התמהיל שהיזם חישב. מוצג ואינו משנה את הרווח. המשפט מהשרת. */
    unit_mix?: {
      rows: { rooms: number; area_sqm: number; units: number }[];
      summary: string | null;
      developer_units?: number;
      tenant_units?: number | null;
      compensation_sqm_per_existing_unit?: number | null;
    };
    /** רק כשיש תרחיש. ההשבחה אינה ידועה — מוצג עד כמה הפרויקט סופג אותה. */
    betterment?: Betterment;
    buildable_basis?: string | null;
    buildable_certainty?: string | null;
    why?: string;
  };
  gaps: {
    unknown_gates: { id: string; label: string; detail: string | null }[];
    unobtainable: { id: string; label: string }[];
    checked_and_not_found: { id: string; label: string }[];
    never_asked: { id: string; label: string }[];
    stale_sources: { id: string; label: string }[];
    economic_inputs_missing: { id: string; label: string }[];
    note: string;
  };
  versions: { rules_version: string; data_version: string; template_version: string };
  delivery: { delivered_at: string | null; why_selected: Record<string, unknown> | null };
  stale_fields: string[];
  /** ‏W4 · מזהה → מונח. ה״?״ שליד תווית נפתח עם ההסבר מכאן. */
  glossary: Record<string, GlossaryEntry>;
}

/** ‏B11 · סף ההשבחה. ‏`viable_up_to_ils` — ההיטל הגבוה ביותר שהרווח עוד סופג. */
export interface Betterment {
  rate: number;
  levy: {
    rate: number;
    viable_up_to_ils: number | null;
    estimate_ils: number | null;
    low_ils: number | null;
    high_ils: number | null;
    within_range: boolean | null;
  };
  estimate: {
    betterment_ils: number; before_ils: number; after_ils: number;
    land_value_per_right_ils: number; notes: string[];
  } | null;
  estimate_withheld_because: string | null;
  breakeven_ils: number | null;
  breakeven_per_added_sqm_ils: number | null;
  breakeven_land_value_per_right_ils: number | null;
  /** ‏`unrated` — אין מחיר דירה קיימת או שטח בנוי קיים, ולכן אין עם מה להשוות את הסף. */
  category: "no_threshold" | "resilient" | "marginal" | "unrated";
  category_label: string;
  /** שורת ההיטל המוכנה (B13) — אותו משפט במסך, ב-PDF ובאקסל. */
  summary: string;
  note: string;
  rests_on_unresolved_inputs: string[];
}

/** התיק המלא. ‏404 גם למי שאינו רשאי וגם למזהה שאינו קיים — ACC-08. */
/** ‏C15 · כמה שורות מלוח הדירות שבהיתר עוד ממתינות לאישור אדם (B3). */
export async function getUnitReviewCounts(opportunityId: string): Promise<{ total: number; pending: number }> {
  const state = await request<{ units: { requires_human_review: boolean }[] }>(
    `/api/v1/dossiers/${opportunityId}/dwelling-units`);
  return { total: state.units.length, pending: state.units.filter((u) => u.requires_human_review).length };
}

export function getDossier(cityCode: string, opportunityId: string): Promise<Dossier> {
  return request<Dossier>(`/api/v1/candidates/${cityCode}/${opportunityId}/dossier`);
}


/**
 * מוריד את התיק כקובץ.
 *
 * לא `<a href>` פשוט: ההורדה חייבת לשאת את טוקן ההרשאה, אחרת השרת מחזיר
 * ‏401 — ו-ACC-08 דורש שגם הייצוא יעבור את אותה בדיקת בעלות כמו התיק.
 * לכן fetch עם הכותרת, ואז blob שמוגש להורדה.
 */
export async function downloadDossier(
  cityCode: string,
  opportunityId: string,
  fmt: "pdf" | "xlsx",
): Promise<void> {
  const token = getToken();
  const response = await fetch(
    `${API_BASE_URL}/api/v1/candidates/${cityCode}/${opportunityId}/dossier.${fmt}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!response.ok) {
    let detail = FALLBACK[response.status] ?? `השרת החזיר ${response.status}.`;
    if (response.status !== 401) {
      try {
        const body = await response.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch { /* לא JSON */ }
    }
    throw new ApiError(response.status, detail);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  // שם הקובץ מגיע מהשרת ב-Content-Disposition; כאן רק גיבוי קריא.
  a.download = `shakdan-${opportunityId.slice(0, 8)}.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
