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
  isRightsRequest,
  runScan,
  type AccountBalance,
  type Candidate,
  type CreditPackage,
  type DeliveredOpportunity,
  type ScanResult,
  type SearchOptions,
} from "@/lib/api";
import Balance from "@/components/Balance";
import VerifyEmailNotice from "@/components/VerifyEmailNotice";
import DeliveredTable from "@/components/DeliveredTable";
import SearchControls from "@/components/SearchControls";
import SearchingOverlay from "@/components/SearchingOverlay";
// מ-`lib` ולא מהקומפוננטה: ייבוא מ-`DrawPolygon` גורר את leaflet
// לחבילת ה-SSR, שם אין `window`, והדף מחזיר 500 בטעינה נקייה.
import { MAX_RADIUS_M, circlePolygon, geodesicArea, type LatLngTuple } from "@/lib/searchArea";
import { RIGHTS_REQUEST_LABEL } from "@/lib/labels";
import { dunam } from "@/lib/format";
import { AppShell } from "@/components/brand/AppShell";
import { IconSearch } from "@/components/brand/icons";
import { assessmentBadge } from "@/components/brand/ui";

const OpportunityMap = dynamic(() => import("@/components/Map"), { ssr: false });

const CITY = "herzliya";
const DEFAULT_RADIUS_M = 200;
const SCAN_SIZE = 3;
const MIN_RADIUS_M = 80;

/** המפה מקבלת מועמדים; הלקוח רואה עליה רק את מה שכבר נמסר לו. */
function asMapRows(mine: DeliveredOpportunity[]): Candidate[] {
  return mine.filter((m) => m.geometry).map((m) => ({
    id: m.opportunity_id, address: m.address, block: m.block, parcel: m.parcel,
    area_sqm: null, verification_level: "", category: null,
    geometry: m.geometry ?? null, centroid: m.centroid ?? null, assessment: m.assessment,
    track: m.why_selected?.track,
  }));
}

/**
 * ‏S2 · הסריקה של הלקוח (בועז, 15.09).
 *
 * **הלקוח אינו רואה מועמדים.** רשימה עם כתובות ממוינות היא המוצר עצמו
 * בחינם. במקומה: לוחץ נקודה על המפה, בוחר רדיוס → ״חפש״ → עד שלושה **תיקים
 * שלמים** מהאזור, מיד (טל, 16.09: בלי שלב ״נמצאו N — לקבל?״ ובלי שליפה
 * מהארכיון בזמן החיפוש). כל תיק שנמסר מנכה זכאות אחת; אזור ריק אינו מחייב.
 * השלושה מופיעים ככרטיסים מתחת למפה ועל המפה עצמה. הרשימה המלאה נשארה
 * לצוות ב-/admin/candidates.
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

  const [result, setResult] = useState<ScanResult | null>(null);
  const [busy, setBusy] = useState<"search" | null>(null);
  const [progress, setProgress] = useState<{ checked: number; found: number } | null>(null);
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
  // בכניסה המפה פתוחה על הרצליה כולה, לא על תיק ישן מהמאגר — אחרת נראה
  // כאילו כבר נסרק משהו. ממקדים רק על מה שהסריקה האחרונה מסרה.
  const fitRows = useMemo(() => asMapRows(result?.delivered ?? []), [result]);

  // אזור החיפוש: העיגול כפוליגון, כמו שהשרת מצפה. השטח נמדד כאן רק כרמז מוקדם.
  const area = useMemo(() => (center ? circlePolygon(center, radiusM) : null), [center, radiusM]);
  const searchArea = area?.polygon ?? null;
  const areaSqm = area ? geodesicArea(area.ring) : 0;

  /** כל שינוי באזור או בתנאים מבטל את התצוגה המקדימה: היא נכונה לשאלה אחרת. */
  function resetScan() {
    setResult(null);
    setError(null);
  }

  function onPick(c: LatLngTuple) {
    setPicking(false);
    setCenter(c);
    setSelectedId(null);
    resetScan();
  }

  /** חיפוש = מסירה: עד שלושה תיקים מהאזור, בלחיצה אחת. מועמד שעוד לא נשלף
   *  נשלף מהארכיון בזמן אמת, אחד-אחד; כשהשרת מחזיר `more` ממשיכים לבד. */
  async function search(acceptRightsRequest = false) {
    if (!searchArea) return;
    setBusy("search");
    setResult(null);
    setError(null);
    setSelectedId(null);
    setProgress({ checked: 0, found: 0 });
    try {
      let r = await runScan(CITY, searchArea, options, false, acceptRightsRequest);
      // ‏`found` של הקריאה הראשונה: בהמשך הוא כבר אינו כולל את מה שנמסר או נבדק
      const found = r.found;
      const delivered = [...r.delivered];
      const skipIds = [...r.skipped_ids];
      let checked = r.checked, skipped = r.skipped;
      while (r.more && delivered.length < SCAN_SIZE && r.credits_remaining > 0) {
        setProgress({ checked, found: delivered.length });
        r = await runScan(CITY, searchArea, options, false, acceptRightsRequest,
                          { want: SCAN_SIZE - delivered.length, skipIds });
        delivered.push(...r.delivered);
        skipIds.push(...r.skipped_ids);
        checked += r.checked;
        skipped += r.skipped;
      }
      setResult({ ...r, delivered, skipped, skipped_ids: skipIds, checked, found });
      if (delivered[0]) setSelectedId(delivered[0].opportunity_id);
    } catch (e) {
      if (signInIfUnauthorized(e)) return;
      // ‏422 הוא MAP-01 עושה את עבודתו, והמשפט בעברית הוא מה שהמשתמש צריך.
      setError(e instanceof ApiError ? e.detail : "החיפוש נכשל. אפשר לנסות שוב.");
    } finally {
      setBusy(null);
      setProgress(null);
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
      ? "לא נותרה זכאות לחברה · בחרו חבילה למעלה כדי להמשיך"
      : center
        ? `אזור של ${dunam(areaSqm)} סביב הנקודה · ״חפש״ מביא עד ${Math.min(3, credits)} תיקים שלמים, וכל תיק מנכה זכאות אחת`
        : `בחר נקודה על המפה, ותקבל עד ${Math.min(3, credits)} תיקי הזדמנות שלמים מסביבה`;

  return (
    <AppShell>
      {busy === "search" && <SearchingOverlay progress={progress} />}
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
            onClick={() => search()}
            disabled={!searchArea || picking || busy !== null || credits < 1}
          >
            {busy === "search" ? "מאתר תיקים…" : <><IconSearch size={14} /> חפש</>}
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

        {/* ‏W6 · בועז, 16.09: חלקה שכלכלית רק עם הגדלת זכויות נמסרת רק בסימון, ואחרי הכלכליות */}
        <label style={{ display: "flex", gap: ".5rem", alignItems: "center", marginTop: ".7rem", fontSize: ".88rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={options.includeRightsRequest ?? false}
            disabled={busy !== null}
            onChange={(e) => { setOptions({ ...options, includeRightsRequest: e.target.checked }); resetScan(); }}
          />
          כולל חלקות שכלכליות רק עם בקשה להגדלת זכויות
          <span className="text-muted">· אחרי הכלכליות לפי המדיניות</span>
        </label>
      </div>

      {showControls && (
        <div style={{ marginBottom: "1rem" }}>
          <SearchControls value={options} onChange={(next) => { setOptions(next); resetScan(); }} />
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
          fitTo={fitRows}
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

      {result?.needs_rights_confirmation && (
        <div className="card tone-warn" style={{ marginBottom: "1rem" }}>
          <strong className="text-warn" style={{ fontSize: "1.05rem" }}>אין באזור חלקה כלכלית לפי המדיניות</strong>
          <p style={{ margin: ".35rem 0 .6rem", fontSize: ".9rem" }}>
            {result.needs_rights_confirmation.count === 1
              ? "נמצאה חלקה אחת שכלכלית רק עם בקשה להגדלת זכויות"
              : `נמצאו ${result.needs_rights_confirmation.count} חלקות שכלכליות רק עם בקשה להגדלת זכויות`}
            . הבקשה אינה מובטחת. <strong>עדיין לא חויבת.</strong>
          </p>
          <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}>
            <button onClick={() => search(true)} disabled={busy !== null || credits < 1}>
              קבל עד {Math.min(3, credits, result.needs_rights_confirmation.count)} תיקים
            </button>
            <button className="btn-secondary" onClick={resetScan} disabled={busy !== null}>לא עכשיו</button>
          </div>
        </div>
      )}

      {result && result.found === 0 && !result.needs_rights_confirmation && (
        <div className="card tone-warn" style={{ marginBottom: "1rem" }}>
          <strong className="text-warn" style={{ fontSize: "1.05rem" }}>אין הזדמנויות באזור הזה</strong>
          <p style={{ margin: ".35rem 0 .2rem", fontSize: ".9rem" }}>
            לא נמצא סביב הנקודה מגרש שעומד בתנאי הסף{conditionsCount > 0 ? " ובתנאים שהגדרת" : ""}. <strong>לא חויבת.</strong>
          </p>
          <p className="text-muted" style={{ margin: 0, fontSize: ".88rem" }}>
            אפשר להגדיל את הרדיוס, לבחור נקודה אחרת{conditionsCount > 0 ? ", או להקל בתנאים" : ""}.
          </p>
          {!options.includeRightsRequest && result.found_rights_request > 0 && (
            <p style={{ margin: ".35rem 0 0", fontSize: ".88rem" }}>
              באזור {result.found_rights_request === 1 ? "יש חלקה אחת" : `יש ${result.found_rights_request} חלקות`} שכלכליות רק עם בקשה להגדלת זכויות. סמנו את האפשרות למעלה כדי לקבל אותן.
            </p>
          )}
        </div>
      )}

      {result && result.found > 0 && (
        <div className={`card ${result.delivered.length > 0 ? "tone-ok" : "tone-warn"}`} style={{ marginBottom: "1rem" }}>
          <strong className={result.delivered.length > 0 ? "text-ok" : "text-warn"} style={{ fontSize: "1.05rem" }}>
            {result.delivered.length === 0
              ? "לא נמסר תיק מהאזור הזה — לא חויבת."
              : `${result.delivered.length === 1 ? "תיק אחד" : `${result.delivered.length} תיקים`} מהאזור · נוכו ${result.delivered.length} זכאויות`}
          </strong>
          {result.skipped > 0 && (
            <p className="text-muted" style={{ margin: ".3rem 0", fontSize: ".88rem" }}>
              {result.skipped === 1 ? "מועמד אחד דולג" : `${result.skipped} מועמדים דולגו`}: התיק לא השלים את תנאי הסף. לא חויבת עליהם.
            </p>
          )}
          {result.message && (
            <p className="text-warn" style={{ margin: ".3rem 0", fontSize: ".88rem", fontWeight: 600 }}>{result.message}</p>
          )}
          {result.delivered.length > 0 && result.delivered.length < 3 && result.credits_remaining > 0 && (
            <p className="text-muted" style={{ margin: ".3rem 0 0", fontSize: ".88rem" }}>
              באזור נמצאו רק {result.delivered.length === 1 ? "תיק אחד" : `${result.delivered.length} תיקים`}. נותרו {result.credits_remaining} זכאויות — אפשר לבחור נקודה נוספת.
            </p>
          )}
        </div>
      )}

      {/* עד שלושה תיקים מהסריקה האחרונה, מתחת למפה; לחיצה על שורה מדגישה את החלקה על המפה.
          ‏16.09 · הכלכליים קודם, ואחריהם — בצהוב ותחת כותרת משלהם — התיקים שכלכליים
          רק עם בקשה להגדלת זכויות. */}
      {result && result.delivered.length > 0 && (() => {
        const shown = result.delivered.slice(0, 3);
        const economic = shown.filter((d) => !isRightsRequest(d));
        const rights = shown.filter(isRightsRequest);
        const card = (d: DeliveredOpportunity) => (
          <div
            key={d.opportunity_id}
            className={`card result${isRightsRequest(d) ? " is-rights" : ""}${selectedId === d.opportunity_id ? " is-selected" : ""}`}
            onClick={() => setSelectedId(d.opportunity_id)}
          >
            <div>
              <strong>{d.address}</strong>
              <div className="text-muted" style={{ fontSize: ".82rem" }}>
                גוש <span className="mono">{d.block ?? "—"}</span> · חלקה <span className="mono">{d.parcel ?? "—"}</span>
              </div>
              <div style={{ marginTop: ".35rem", display: "flex", gap: ".4rem", flexWrap: "wrap", alignItems: "center" }}>
                {d.assessment ? assessmentBadge(d.assessment.status) : null}
                {isRightsRequest(d) && <span className="pill rights">נדרשת הגדלת זכויות</span>}
              </div>
            </div>
            <Link href={`/app/dossier/${d.opportunity_id}`} className="sk-btn-like" onClick={(e) => e.stopPropagation()}>
              פתח תיק ←
            </Link>
          </div>
        );
        return (
          <>
            {economic.length > 0 && <div className="results">{economic.map(card)}</div>}
            {rights.length > 0 && (
              <div>
                <h3 className="results-title">{RIGHTS_REQUEST_LABEL}</h3>
                <div className="results">{rights.map(card)}</div>
              </div>
            )}
          </>
        );
      })()}

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
