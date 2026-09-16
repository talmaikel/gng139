"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  getBalance,
  getMyDeliveries,
  getPackages,
  previewScan,
  runScan,
  type AccountBalance,
  type Candidate,
  type CreditPackage,
  type DeliveredOpportunity,
  type ScanPreview,
  type ScanResult,
  type SearchOptions,
} from "@/lib/api";
import Balance from "@/components/Balance";
import VerifyEmailNotice from "@/components/VerifyEmailNotice";
import DeliveredTable from "@/components/DeliveredTable";
import SearchControls from "@/components/SearchControls";
// מ-`lib` ולא מהקומפוננטה: ייבוא מ-`DrawPolygon` גורר את leaflet
// לחבילת ה-SSR, שם אין `window`, והדף מחזיר 500 בטעינה נקייה.
import { MAX_AREA_SQM } from "@/lib/searchArea";

const OpportunityMap = dynamic(() => import("@/components/Map"), { ssr: false });

const CITY = "herzliya";
const dunam = (sqm: number) => `${(sqm / 1000).toFixed(1)} דונם`;

/** המפה מקבלת מועמדים; הלקוח רואה עליה רק את מה שכבר נמסר לו. */
function asMapRows(mine: DeliveredOpportunity[]): Candidate[] {
  return mine.filter((m) => m.geometry).map((m) => ({
    id: m.opportunity_id, address: m.address, block: m.block, parcel: m.parcel,
    area_sqm: null, verification_level: "", category: null,
    geometry: m.geometry ?? null, centroid: m.centroid ?? null, assessment: m.assessment,
  }));
}

/**
 * ‏S2 · הסריקה של הלקוח (בועז, 15.09).
 *
 * **הלקוח אינו רואה מועמדים.** רשימה עם כתובות ממוינות היא המוצר עצמו
 * בחינם. במקומה: מצייר אזור → ״חפש״ → *״נמצאו N — לקבל?״* → עד שלושה תיקים,
 * לפי התנאים וההעדפות שלו, מוכנים קודם. נמצאו פחות משלושה — הזכאות שנשארה
 * משמשת לאזור הבא. הרשימה המלאה נשארה לצוות ב-/admin/candidates.
 */
export default function DashboardPage() {
  const router = useRouter();

  const [tab, setTab] = useState<"search" | "mine">("search");
  const [balance, setBalance] = useState<AccountBalance | null>(null);
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [mine, setMine] = useState<DeliveredOpportunity[]>([]);

  const [drawing, setDrawing] = useState(false);
  const [searchArea, setSearchArea] = useState<object | null>(null);
  const [liveArea, setLiveArea] = useState<{ points: number; sqm: number } | null>(null);
  const [options, setOptions] = useState<SearchOptions>({});
  const [showControls, setShowControls] = useState(false);

  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "deliver" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const signInIfUnauthorized = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      router.replace("/login");
      return true;
    }
    return false;
  }, [router]);

  const loadAccount = useCallback(() => {
    getBalance().then(setBalance).catch((e) => { if (!signInIfUnauthorized(e)) setBalance(null); });
    getMyDeliveries(CITY).then(setMine).catch(() => setMine([]));
  }, [signInIfUnauthorized]);

  useEffect(() => {
    loadAccount();
    getPackages().then(setPackages).catch(() => setPackages([]));
  }, [loadAccount]);

  const credits = balance?.credits_remaining ?? 0;
  // ‏useMemo ולא חישוב ב-render: המפה ממקדת את עצמה מחדש בכל פעם שהמערך
  // מתחלף, ומערך חדש בכל render החזיר אותה לחלקות בכל הקלדה — המשתמש לא
  // יכול היה להתרחק כדי לצייר אזור.
  const mapRows = useMemo(() => asMapRows(mine), [mine]);

  /** כל שינוי באזור או בתנאים מבטל את התצוגה המקדימה: היא נכונה לשאלה אחרת. */
  function resetScan() {
    setPreview(null);
    setResult(null);
    setError(null);
  }

  function onPolygon(polygon: object) {
    setDrawing(false);
    setLiveArea(null);
    setSearchArea(polygon);
    resetScan();
  }

  async function search() {
    if (!searchArea) return;
    setBusy("preview");
    setResult(null);
    setError(null);
    try {
      setPreview(await previewScan(CITY, searchArea, options));
    } catch (e) {
      if (signInIfUnauthorized(e)) return;
      // ‏422 הוא MAP-01 עושה את עבודתו, והמשפט בעברית הוא מה שהמשתמש צריך.
      setError(e instanceof ApiError ? e.detail : "החיפוש נכשל.");
    } finally {
      setBusy(null);
    }
  }

  async function accept() {
    if (!searchArea) return;
    setBusy("deliver");
    setError(null);
    try {
      setResult(await runScan(CITY, searchArea, options));
      setPreview(null);
    } catch (e) {
      if (signInIfUnauthorized(e)) return;
      setError(e instanceof ApiError
        ? (e.status === 402 ? `${e.detail}` : e.detail)
        : "המסירה נכשלה. אפשר לנסות שוב.");
    } finally {
      setBusy(null);
      loadAccount();
    }
  }

  const conditionsCount =
    [options.minAreaSqm, options.minUnits, options.minFloors, options.minCap400Sqm]
      .filter((v) => v !== undefined).length
    + (options.certainFloorsOnly ? 1 : 0) + (options.preferences?.length ?? 0);
  const overLimit = liveArea !== null && liveArea.points >= 3 && liveArea.sqm > MAX_AREA_SQM;

  return (
    <main className="page" style={{ maxWidth: 1100 }}>
      <h1 style={{ marginBottom: "1rem" }}>חלופת שקד · הרצליה</h1>

      <VerifyEmailNotice />

      <div style={{ marginBottom: "1rem" }}>
        <Balance balance={balance} packages={packages} onChanged={loadAccount} />
      </div>

      <div style={{ display: "flex", gap: ".4rem", marginBottom: "1rem" }}>
        {([["search", "סריקה"], ["mine", `המאגר שלי${mine.length ? ` · ${mine.length}` : ""}`]] as const).map(
          ([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              style={{
                background: tab === key ? "#1f6f4f" : "transparent",
                color: tab === key ? "#fff" : "#1a1a1a",
                border: tab === key ? "none" : "1px solid #d8d8d3",
              }}
            >
              {label}
            </button>
          )
        )}
      </div>

      {tab === "mine" ? (
        <div className="card">
          <DeliveredTable rows={mine} />
        </div>
      ) : (
      <>
      <div className="card" style={{ marginBottom: "1rem", padding: "0.9rem 1.1rem" }}>
        <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap" }}>
          {!drawing ? (
            <button onClick={() => { setDrawing(true); setLiveArea(null); resetScan(); }}
                    style={searchArea ? { background: "transparent", color: "#1a1a1a", border: "1px solid #d8d8d3" } : undefined}>
              ✏️ {searchArea ? "צייר אזור אחר" : "צייר אזור חיפוש"}
            </button>
          ) : (
            <button onClick={() => { setDrawing(false); setLiveArea(null); }} style={{ background: "#6b655c" }}>
              בטל ציור
            </button>
          )}

          <button
            onClick={() => setShowControls((v) => !v)}
            style={{ background: "transparent", color: "#1a1a1a", border: "1px solid #d8d8d3" }}
          >
            תנאים והעדפות
            {conditionsCount > 0 && (
              <span style={{ color: "#1f6f4f", fontWeight: 700 }}> · {conditionsCount}</span>
            )}
          </button>

          <button
            onClick={search}
            disabled={!searchArea || drawing || busy !== null || credits < 1}
            style={{ background: "#1d4e89", fontWeight: 700 }}
          >
            {busy === "preview" ? "מחפש…" : "🔍 חפש"}
          </button>

          <span style={{ color: "#6b655c", fontSize: ".88rem" }}>
            {drawing
              ? liveArea === null
                ? "לחיצה מוסיפה קודקוד · לחיצה כפולה או Enter לסיום · Escape לביטול"
                : `${liveArea.points} קודקודים · ${dunam(liveArea.sqm)}`
              : credits < 1
                ? "לא נותרה זכאות לחברה"
                : searchArea
                  ? "האזור מסומן — אפשר להגדיר תנאים וללחוץ ״חפש״"
                  : `צייר אזור על המפה, ותקבל עד ${Math.min(3, credits)} תיקי הזדמנות ממנו`}
          </span>

          {overLimit && (
            <span style={{ color: "#a8321e", fontWeight: 600, fontSize: ".88rem" }}>
              מעל מגבלת {MAX_AREA_SQM / 1000} הדונם — השרת ידחה
            </span>
          )}
        </div>
      </div>

      {showControls && (
        <div style={{ marginBottom: "1rem" }}>
          <SearchControls value={options} onChange={(next) => { setOptions(next); resetScan(); }} />
        </div>
      )}

      {preview && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "#bcd0e6", background: "#f3f7fc" }}>
          {preview.offer > 0 ? (
            <>
              <strong style={{ fontSize: "1.05rem", color: "#1d4e89" }}>
                נמצאו {preview.found} מועמדים באזור · תקבל {preview.offer === 1 ? "תיק אחד" : `${preview.offer} תיקים`}
              </strong>
              <p style={{ margin: ".35rem 0 .8rem", color: "#3d4a5c", fontSize: ".9rem" }}>
                {preview.ready > 0 && `${preview.ready} מוכנים מיד`}
                {preview.ready > 0 && preview.needs_fetch > 0 && " · "}
                {preview.needs_fetch > 0 && `${preview.needs_fetch} ישלפו תיק בניין מהארכיון (עד 20 שניות לכל אחד)`}
                {" · "}ינוכו עד {preview.offer} זכאויות, ורק על תיק שנמסר.
              </p>
              <div style={{ display: "flex", gap: ".6rem" }}>
                <button onClick={accept} disabled={busy !== null} style={{ background: "#1f6f4f", fontWeight: 700 }}>
                  {busy === "deliver"
                    ? (preview.needs_fetch > 0 ? "שולף תיקי בניין…" : "מוסר…")
                    : `קבל ${preview.offer === 1 ? "תיק אחד" : `${preview.offer} תיקים`}`}
                </button>
                <button onClick={resetScan} disabled={busy !== null}
                        style={{ background: "transparent", color: "#6b655c", border: "1px solid #d8d8d3" }}>
                  ביטול
                </button>
              </div>
            </>
          ) : preview.credits_remaining < 1 ? (
            <strong style={{ color: "#8a6100" }}>לא נותרה זכאות לחברה. יש לרכוש חבילה כדי להמשיך.</strong>
          ) : (
            <strong style={{ color: "#8a6100" }}>
              לא נמצאו מועמדים באזור שעומדים בתנאים — לא חויבת. אפשר לצייר אזור אחר או לשנות את התנאים.
            </strong>
          )}
        </div>
      )}

      {result && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "#c8ddd2", background: "#f3f9f6" }}>
          <strong style={{ fontSize: "1.05rem", color: "#1f5f55" }}>
            {result.delivered.length === 0
              ? "לא נמסר תיק מהאזור הזה — לא חויבת."
              : `נמסרו ${result.delivered.length === 1 ? "תיק אחד" : `${result.delivered.length} תיקים`} · נוכו ${result.delivered.length} זכאויות`}
          </strong>
          {result.delivered.length > 0 && (
            <ul style={{ margin: ".5rem 0", paddingInlineStart: "1.1rem" }}>
              {result.delivered.map((d) => (
                <li key={d.opportunity_id} style={{ marginBottom: ".2rem" }}>
                  <Link href={`/dossier/${d.opportunity_id}`} style={{ fontWeight: 600 }}>
                    {d.address} ←
                  </Link>
                  <span style={{ color: "#6b655c", fontSize: ".85rem" }}> · גוש {d.block} חלקה {d.parcel}</span>
                </li>
              ))}
            </ul>
          )}
          {result.skipped > 0 && (
            <p style={{ margin: ".3rem 0", color: "#6b655c", fontSize: ".88rem" }}>
              {result.skipped === 1 ? "מועמד אחד דולג" : `${result.skipped} מועמדים דולגו`}: תיק הבניין לא השלים את תנאי הסף. לא חויבת עליהם.
            </p>
          )}
          {result.message && (
            <p style={{ margin: ".3rem 0", color: "#8a6100", fontSize: ".88rem", fontWeight: 600 }}>{result.message}</p>
          )}
          <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap", marginTop: ".4rem" }}>
            {result.retryable && result.credits_remaining > 0 && (
              <button onClick={accept} disabled={busy !== null}>
                {busy === "deliver" ? "שולף…" : "השלם את החיפוש באזור"}
              </button>
            )}
            {!result.retryable && result.delivered.length < result.requested && result.credits_remaining > 0 && (
              <span style={{ color: "#1f5f55", fontSize: ".88rem" }}>
                נותרו {result.credits_remaining} זכאויות — אפשר לצייר אזור נוסף.
              </span>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "#e6c9c2", background: "#fdf6f4" }}>
          <strong style={{ color: "#a8321e" }}>{error}</strong>
        </div>
      )}

      <div className="card" style={{ marginBottom: "1.2rem", padding: 0, overflow: "hidden" }}>
        <OpportunityMap
          candidates={mapRows}
          drawing={drawing}
          searchArea={searchArea}
          onPolygon={onPolygon}
          onCancelDraw={() => { setDrawing(false); setLiveArea(null); }}
          onDrawProgress={(points, sqm) => setLiveArea({ points, sqm })}
        />
      </div>
      {mine.length > 0 && (
        <p style={{ color: "#6b655c", fontSize: ".82rem", marginTop: "-.6rem" }}>
          על המפה מסומנים רק התיקים שכבר קיבלת.
        </p>
      )}
      </>
      )}
    </main>
  );
}
