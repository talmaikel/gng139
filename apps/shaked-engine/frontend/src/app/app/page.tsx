"use client";

import { Slider } from "@mantine/core";
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
import { MAX_RADIUS_M, circlePolygon, geodesicArea, type LatLngTuple } from "@/lib/searchArea";
import { dunam } from "@/lib/format";
import { AppShell } from "@/components/brand/AppShell";
import { IconSearch } from "@/components/brand/icons";
import { assessmentBadge } from "@/components/brand/ui";

const OpportunityMap = dynamic(() => import("@/components/Map"), { ssr: false });

const CITY = "herzliya";
const DEFAULT_RADIUS_M = 200;
const MIN_RADIUS_M = 80;

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
 * בחינם. במקומה: לוחץ נקודה על המפה, בוחר רדיוס → ״חפש״ → *״נמצאו N — לקבל?״*
 * → עד שלושה תיקים, לפי התנאים וההעדפות שלו, מוכנים קודם. השלושה שנמסרו
 * מופיעים ברשימה מתחת למפה ועל המפה עצמה. הרשימה המלאה נשארה לצוות
 * ב-/admin/candidates.
 */
export default function DashboardPage() {
  const router = useRouter();

  const [tab, setTab] = useState<"search" | "mine">("search");
  // הקישור ״המאגר שלי״ בכותרת מגיע לכאן עם #mine.
  useEffect(() => {
    const pick = () => setTab(window.location.hash === "#mine" ? "mine" : "search");
    pick();
    window.addEventListener("hashchange", pick);
    return () => window.removeEventListener("hashchange", pick);
  }, []);
  const [balance, setBalance] = useState<AccountBalance | null>(null);
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [mine, setMine] = useState<DeliveredOpportunity[]>([]);

  const [picking, setPicking] = useState(false);
  const [center, setCenter] = useState<LatLngTuple | null>(null);
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [options, setOptions] = useState<SearchOptions>({});
  const [showControls, setShowControls] = useState(false);

  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [busy, setBusy] = useState<"preview" | "deliver" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
  // יכול היה להתרחק כדי לבחור נקודה.
  const mapRows = useMemo(() => asMapRows(mine), [mine]);

  // אזור החיפוש: העיגול כפוליגון, כמו שהשרת מצפה. השטח נמדד כאן רק כרמז מוקדם.
  const area = useMemo(() => (center ? circlePolygon(center, radiusM) : null), [center, radiusM]);
  const searchArea = area?.polygon ?? null;
  const areaSqm = area ? geodesicArea(area.ring) : 0;

  /** כל שינוי באזור או בתנאים מבטל את התצוגה המקדימה: היא נכונה לשאלה אחרת. */
  function resetScan() {
    setPreview(null);
    setResult(null);
    setError(null);
  }

  function onPick(c: LatLngTuple) {
    setPicking(false);
    setCenter(c);
    setSelectedId(null);
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

  const hint = picking
    ? "לחיצה על המפה קובעת את מרכז החיפוש · Escape לביטול"
    : credits < 1
      ? "לא נותרה זכאות לחברה"
      : center
        ? `אזור של ${dunam(areaSqm)} סביב הנקודה — אפשר להגדיר תנאים וללחוץ ״חפש״`
        : `בחר נקודה על המפה, ותקבל עד ${Math.min(3, credits)} תיקי הזדמנות מסביבה`;

  return (
    <AppShell>
      <p className="eyebrow">חלופת שקד · הרצליה</p>
      <h1 style={{ margin: ".15rem 0 1rem" }}>האזור האישי</h1>

      <VerifyEmailNotice />

      <div style={{ marginBottom: "1rem" }}>
        <Balance balance={balance} packages={packages} onChanged={loadAccount} />
      </div>

      <div className="tabs" role="tablist">
        {([["search", "סריקה"], ["mine", `המאגר שלי${mine.length ? ` · ${mine.length}` : ""}`]] as const).map(
          ([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} data-active={tab === key || undefined}
                    onClick={() => setTab(key)}>
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
          {!picking ? (
            <button className={center ? "btn-secondary" : "btn-dark"} onClick={() => { setPicking(true); resetScan(); }}>
              ◎ {center ? "בחר נקודה אחרת" : "בחר נקודה על המפה"}
            </button>
          ) : (
            <button className="btn-secondary" onClick={() => setPicking(false)}>
              בטל בחירה
            </button>
          )}

          <button className="btn-secondary" onClick={() => setShowControls((v) => !v)}>
            תנאים והעדפות
            {conditionsCount > 0 && (
              <span className="text-warn"> · {conditionsCount}</span>
            )}
          </button>

          <button
            onClick={search}
            disabled={!searchArea || picking || busy !== null || credits < 1}
          >
            {busy === "preview" ? "מחפש…" : <><IconSearch size={14} /> חפש</>}
          </button>

          <span className="text-muted" style={{ fontSize: ".88rem" }}>{hint}</span>
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--rule-2)" }}>
          <span style={{ fontSize: ".85rem", fontWeight: 600 }}>רדיוס החיפוש</span>
          <Slider
            style={{ flex: "1 1 220px", maxWidth: 360 }}
            min={MIN_RADIUS_M} max={MAX_RADIUS_M} step={10}
            value={radiusM}
            onChange={(v) => { setRadiusM(v); resetScan(); }}
            label={(v) => `${v} מ׳`}
            marks={[{ value: 100, label: "100 מ׳" }, { value: 200, label: "200 מ׳" }, { value: MAX_RADIUS_M, label: `${MAX_RADIUS_M} מ׳` }]}
            disabled={busy !== null}
          />
          <span className="num text-muted" style={{ fontSize: ".85rem", minWidth: "7rem" }}>
            {radiusM} מ׳ · {dunam(Math.PI * radiusM * radiusM)}
          </span>
        </div>
      </div>

      {showControls && (
        <div style={{ marginBottom: "1rem" }}>
          <SearchControls value={options} onChange={(next) => { setOptions(next); resetScan(); }} />
        </div>
      )}

      {preview && (
        <div className="card tone-info" style={{ marginBottom: "1rem" }}>
          {preview.offer > 0 ? (
            <>
              <strong style={{ fontSize: "1.05rem" }}>
                נמצאו {preview.found} מועמדים באזור · תקבל {preview.offer === 1 ? "תיק אחד" : `${preview.offer} תיקים`}
              </strong>
              <p className="text-muted" style={{ margin: ".35rem 0 .8rem", fontSize: ".9rem" }}>
                {preview.ready > 0 && `${preview.ready} מוכנים מיד`}
                {preview.ready > 0 && preview.needs_fetch > 0 && " · "}
                {preview.needs_fetch > 0 && `${preview.needs_fetch} ישלפו תיק בניין מהארכיון (עד 20 שניות לכל אחד)`}
                {" · "}ינוכו עד {preview.offer} זכאויות, ורק על תיק שנמסר.
              </p>
              <div style={{ display: "flex", gap: ".6rem" }}>
                <button onClick={accept} disabled={busy !== null}>
                  {busy === "deliver"
                    ? (preview.needs_fetch > 0 ? "שולף תיקי בניין…" : "מוסר…")
                    : `קבל ${preview.offer === 1 ? "תיק אחד" : `${preview.offer} תיקים`}`}
                </button>
                <button className="btn-ghost" onClick={resetScan} disabled={busy !== null}>
                  ביטול
                </button>
              </div>
            </>
          ) : preview.credits_remaining < 1 ? (
            <strong className="text-warn">לא נותרה זכאות לחברה. יש לרכוש חבילה כדי להמשיך.</strong>
          ) : (
            <strong className="text-warn">
              לא נמצאו מועמדים באזור שעומדים בתנאים — לא חויבת. אפשר לבחור נקודה אחרת או לשנות את התנאים.
            </strong>
          )}
        </div>
      )}

      {error && (
        <div className="card tone-bad" style={{ marginBottom: "1rem" }}>
          <strong className="text-bad">{error}</strong>
        </div>
      )}

      <div className="card" style={{ marginBottom: "1.2rem", padding: 0, overflow: "hidden" }}>
        <OpportunityMap
          candidates={mapRows}
          mode="circle"
          drawing={picking}
          circle={center ? { center, radiusM } : null}
          onPick={onPick}
          onCancelDraw={() => setPicking(false)}
          selectedId={selectedId}
          onSelect={setSelectedId}
          dossierHref={(id) => `/app/dossier/${id}`}
        />
      </div>

      {result && (
        <div className="card tone-ok" style={{ marginBottom: "1rem" }}>
          <strong className="text-ok" style={{ fontSize: "1.05rem" }}>
            {result.delivered.length === 0
              ? "לא נמסר תיק מהאזור הזה — לא חויבת."
              : `נמסרו ${result.delivered.length === 1 ? "תיק אחד" : `${result.delivered.length} תיקים`} · נוכו ${result.delivered.length} זכאויות`}
          </strong>
          {result.skipped > 0 && (
            <p className="text-muted" style={{ margin: ".3rem 0", fontSize: ".88rem" }}>
              {result.skipped === 1 ? "מועמד אחד דולג" : `${result.skipped} מועמדים דולגו`}: תיק הבניין לא השלים את תנאי הסף. לא חויבת עליהם.
            </p>
          )}
          {result.message && (
            <p className="text-warn" style={{ margin: ".3rem 0", fontSize: ".88rem", fontWeight: 600 }}>{result.message}</p>
          )}
          <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap", marginTop: ".4rem" }}>
            {result.retryable && result.credits_remaining > 0 && (
              <button onClick={accept} disabled={busy !== null}>
                {busy === "deliver" ? "שולף…" : "השלם את החיפוש באזור"}
              </button>
            )}
            {!result.retryable && result.delivered.length < result.requested && result.credits_remaining > 0 && (
              <span className="text-ok" style={{ fontSize: ".88rem" }}>
                נותרו {result.credits_remaining} זכאויות — אפשר לבחור נקודה נוספת.
              </span>
            )}
          </div>
        </div>
      )}

      {/* עד שלושה תיקים מהסריקה האחרונה, מתחת למפה; לחיצה על שורה מדגישה את החלקה על המפה */}
      {result && result.delivered.length > 0 && (
        <div className="results">
          {result.delivered.slice(0, 3).map((d) => (
            <div
              key={d.opportunity_id}
              className={`card result${selectedId === d.opportunity_id ? " is-selected" : ""}`}
              onClick={() => setSelectedId(d.opportunity_id)}
            >
              <div>
                <strong>{d.address}</strong>
                <div className="text-muted" style={{ fontSize: ".82rem" }}>
                  גוש <span className="mono">{d.block ?? "—"}</span> · חלקה <span className="mono">{d.parcel ?? "—"}</span>
                </div>
                <div style={{ marginTop: ".35rem" }}>{d.assessment ? assessmentBadge(d.assessment.status) : null}</div>
              </div>
              <Link href={`/app/dossier/${d.opportunity_id}`} className="sk-btn-like" onClick={(e) => e.stopPropagation()}>
                פתח תיק ←
              </Link>
            </div>
          ))}
        </div>
      )}

      {mine.length > 0 && !result && (
        <p className="text-muted" style={{ fontSize: ".82rem", marginTop: "-.6rem" }}>
          על המפה מסומנים רק התיקים שכבר קיבלת. לחיצה על חלקה פותחת את התיק.
        </p>
      )}
      </>
      )}
    </AppShell>
  );
}
