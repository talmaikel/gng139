/** ‏W8 · מחשבון התרחיש: הכלכלה של התיק לפי מה שהיזם שינה, והייצוא שלה.
 *
 *  בקובץ נפרד מ-`api.ts` כדי שעבודה על מסכים אחרים לא תיגע באותו קובץ. ההרשאה
 *  כמו ב-`api.ts`: אותו טוקן, ו-`ApiError` עם המשפט שהשרת כתב. שום דבר אינו נשמר. */
import { ApiError } from "@/lib/api";
import type { ScenarioOverrides, ScenarioResponse } from "@/lib/dossier";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** אותו מפתח שבו `api.ts` שומר את הטוקן. */
function token(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("shaked_token");
}

const FALLBACK: Record<number, string> = {
  401: "נדרשת התחברות מחדש.",
  404: "התיק אינו במאגר החברה.",
  422: "אחד הערכים אינו בטווח שאפשר לחשב.",
  503: "שירות חיצוני אינו זמין כרגע. אפשר לנסות שוב בעוד כמה דקות.",
};

async function post(path: string, body: ScenarioOverrides, signal?: AbortSignal): Promise<Response> {
  const t = token();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let detail = FALLBACK[response.status] ?? `השרת החזיר ${response.status}.`;
    if (response.status !== 401) {
      try {
        const data = await response.json();
        // ‏422 מהמחשבון הוא משפט (תמהיל שאינו נכנס); ‏422 של אימות שדות הוא רשימה, ונשאר הכללי.
        if (typeof data?.detail === "string") detail = data.detail;
      } catch { /* לא JSON */ }
    }
    throw new ApiError(response.status, detail);
  }
  return response;
}

export async function runScenario(cityCode: string, opportunityId: string, body: ScenarioOverrides,
                                  signal?: AbortSignal): Promise<ScenarioResponse> {
  const response = await post(`/api/v1/candidates/${cityCode}/${opportunityId}/dossier/scenario`, body, signal);
  return response.json() as Promise<ScenarioResponse>;
}

/** התרחיש כקובץ — כמו `downloadDossier`, ב-POST עם הערכים שהיזם שינה. */
export async function downloadScenario(cityCode: string, opportunityId: string, fmt: "pdf" | "xlsx",
                                       body: ScenarioOverrides): Promise<void> {
  const response = await post(`/api/v1/candidates/${cityCode}/${opportunityId}/dossier.${fmt}`, body);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `shakdan-${opportunityId.slice(0, 8)}-scenario.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
