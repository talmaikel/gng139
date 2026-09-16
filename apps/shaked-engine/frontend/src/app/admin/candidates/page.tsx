"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  isRetryable,
  deliverOpportunity,
  getBalance,
  getCandidates,
  getMyDeliveries,
  getPackages,
  searchCandidates,
  type AccountBalance,
  type Assessment,
  type Candidate,
  type CreditPackage,
  type DeliveredOpportunity,
  type SearchOptions,
} from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";

import Balance from "@/components/Balance";
import DeliveredTable from "@/components/DeliveredTable";
import SearchControls from "@/components/SearchControls";
// מ-`lib` ולא מהקומפוננטה: ייבוא מ-`DrawPolygon` גורר את leaflet
// לחבילת ה-SSR, שם אין `window`, והדף מחזיר 500 בטעינה נקייה.
import { MAX_AREA_SQM } from "@/lib/searchArea";
import { dunam } from "@/lib/format";
import { AppShell } from "@/components/brand/AppShell";
import { assessmentBadge } from "@/components/brand/ui";
import { IconPencil } from "@/components/brand/icons";

/** Gate ids come from the rules engine in English. A developer reading the screen
 *  should see what is missing, not a field name. */
const GATE_LABEL: Record<string, string> = {
  residential_zoning: "ייעוד למגורים",
  residential_share: "70% שימוש למגורים",
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

/** מזהי שערים שמגיעים בתוך משפט מהשרת. הוא כותב אותם באנגלית כי הם מזהים
 *  בקוד — ומה שמוצג לאדם צריך להיות בשפה שלו. */
const localiseGates = (text: string) =>
  Object.entries(GATE_LABEL).reduce(
    (out, [id, label]) => out.replace(new RegExp(`\\b${id}\\b`, "g"), label),
    text
  );

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

export default function LegacyCandidatesPage() {
  const router = useRouter();

  /** ‏401 פירושו שאין טוקן תקף — לא תקלה שצריך להציג, אלא התחברות שצריך
   *  לבקש. בלי זה מי שפותח קישור לאפליקציה רואה מסך ריק עם הודעת שגיאה
   *  מתחת למפה, ומסיק שהיא שבורה. */
  const signInIfUnauthorized = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      router.replace("/login");
      return true;
    }
    return false;
  }, [router]);

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [tab, setTab] = useState<"search" | "mine">("search");
  const [balance, setBalance] = useState<AccountBalance | null>(null);
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [mine, setMine] = useState<DeliveredOpportunity[]>([]);
  const [delivering, setDelivering] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  /** מועמד שנכשל על תקלה חיצונית — ראוי לכפתור ״נסה שוב״ ולא לוויתור */
  const [retryable, setRetryable] = useState<Candidate | null>(null);

  const [drawing, setDrawing] = useState(false);
  const [searchArea, setSearchArea] = useState<object | null>(null);
  const [liveArea, setLiveArea] = useState<{ points: number; sqm: number } | null>(null);
  const [options, setOptions] = useState<SearchOptions>({});
  const [showControls, setShowControls] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError(null);
    getCandidates(DEFAULT_CITY)
      .then(setCandidates)
      .catch((e) => {
        if (signInIfUnauthorized(e)) return;
        setError(e instanceof ApiError ? e.detail : "לא ניתן לטעון מועמדים. האם השרת רץ?");
      })
      .finally(() => setLoading(false));
  }, [signInIfUnauthorized]);

  /** יתרה ומאגר נטענים יחד: שניהם משתנים בכל מסירה, ושניהם של החברה. */
  const loadAccount = useCallback(() => {
    getBalance().then(setBalance).catch(() => setBalance(null));
    getMyDeliveries(DEFAULT_CITY).then(setMine).catch(() => setMine([]));
  }, []);

  useEffect(loadAll, [loadAll]);
  useEffect(() => {
    loadAccount();
    getPackages().then(setPackages).catch(() => setPackages([]));
  }, [loadAccount]);

  const deliveredIds = new Set(mine.map((m) => m.opportunity_id));

  async function deliver(candidate: Candidate) {
    setDelivering(candidate.id);
    setNotice(null);
    setError(null);
    setRetryable(null);
    try {
      const result = await deliverOpportunity(DEFAULT_CITY, candidate.id);
      // ‏ACC-02: תוצאה שכבר נמסרה אינה מחייבת שוב. ההודעה אומרת את זה
      // במפורש, אחרת יתרה שלא זזה נראית כמו תקלה.
      setNotice(
        result.charged
          ? `${candidate.address} נמסר. נוכתה זכאות אחת.`
          : `${candidate.address} כבר נמסר לחברה — ללא חיוב נוסף.`
      );
      loadAccount();
      // המגרש יוצא מרשימת ההצעות: SEL-02, "מוצג במאגר החברה בלבד".
      setCandidates((prev) => prev.filter((c) => c.id !== candidate.id));
    } catch (e) {
      if (e instanceof ApiError) {
        // ‏409 אינו 402. ״אינו מוכן״ ו״אין יתרה״ מובילים לפעולות שונות,
        // ולכן אסור להם להיראות כאותה הודעה.
        setError(
          e.status === 402
            ? `${e.detail} יש לרכוש חבילה כדי להמשיך.`
            : localiseGates(e.detail)
        );
        // ‏503 אינו תשובה על המועמד. בלי ההבחנה הזו הלקוח מוותר על מגרש
        // תקין לחלוטין כי הארכיון היה עסוק לרגע.
        if (isRetryable(e)) setRetryable(candidate);
      } else {
        setError("המסירה נכשלה.");
      }
    } finally {
      setDelivering(null);
    }
  }

  const runSearch = useCallback((polygon: object, opts: SearchOptions) => {
    setLoading(true);
    setError(null);
    searchCandidates(DEFAULT_CITY, polygon, opts)
      .then(setCandidates)
      // ‏422 כאן אינו תקלה אלא MAP-01 עושה את עבודתו, והמשפט בעברית הוא
      // מה שהמשתמש צריך לפעול לפיו — ולכן הוא מוצג כמו שהוא.
      .catch((e) => {
        setError(e instanceof ApiError ? e.detail : "החיפוש נכשל.");
        setCandidates([]);
      })
      .finally(() => setLoading(false));
  }, []);

  function onPolygon(polygon: object, areaSqm: number) {
    setDrawing(false);
    setLiveArea(null);
    setSearchArea(polygon);
    setSelectedId(null);
    runSearch(polygon, options);
  }

  function clearArea() {
    setSearchArea(null);
    setSelectedId(null);
    loadAll();
  }

  const activeConditions = [
    options.minAreaSqm !== undefined && `שטח ≥ ${options.minAreaSqm}`,
    options.minUnits !== undefined && `דירות ≥ ${options.minUnits}`,
    options.minFloors !== undefined && `קומות ≥ ${options.minFloors}`,
    options.minCap400Sqm !== undefined && `תקרה ≥ ${options.minCap400Sqm}`,
    options.certainFloorsOnly && "קומות ודאיות",
  ].filter(Boolean) as string[];

  const overLimit = liveArea !== null && liveArea.points >= 3 && liveArea.sqm > MAX_AREA_SQM;

  return (
    <AppShell>
      <p className="eyebrow">חלופת שקד · ניהול</p>
      <h1 style={{ margin: ".15rem 0 .4rem" }}>כל המועמדים</h1>
      {/* ‏S2 · הרשימה המלאה הוחלפה אצל הלקוח בסריקה (/app). הדף הזה
          נשאר לצוות כגיבוי להדגמה של 16.09, ואינו מקושר מהמסך של הלקוח. */}
      <p className="text-warn" style={{ margin: "0 0 1rem", fontSize: ".85rem" }}>
        מסך צוות · רשימת כל המועמדים (גיבוי). הלקוח רואה את הסריקה ב-<Link href="/app">/app</Link>.
      </p>

      <div style={{ marginBottom: "1rem" }}>
        <Balance balance={balance} packages={packages} onChanged={loadAccount} />
      </div>

      <div className="tabs" role="tablist">
        {([["search", "חיפוש"], ["mine", `המאגר שלי${mine.length ? ` · ${mine.length}` : ""}`]] as const).map(
          ([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} data-active={tab === key || undefined}
                    onClick={() => setTab(key)}>
              {label}
            </button>
          )
        )}
      </div>

      {notice && (
        <div className="card tone-ok" style={{ marginBottom: "1rem" }}>
          <strong className="text-ok">{notice}</strong>
        </div>
      )}

      {tab === "mine" ? (
        <div className="card">
          <DeliveredTable rows={mine} />
        </div>
      ) : (
      <>
      <div className="card" style={{ marginBottom: "1rem", padding: "0.9rem 1.1rem" }}>
        <div style={{ display: "flex", gap: ".6rem", alignItems: "center", flexWrap: "wrap" }}>
          {!drawing ? (
            <button className="btn-dark" onClick={() => { setDrawing(true); setLiveArea(null); }}>
              <IconPencil size={14} /> צייר אזור חיפוש
            </button>
          ) : (
            <button className="btn-secondary" onClick={() => { setDrawing(false); setLiveArea(null); }}>
              בטל ציור
            </button>
          )}

          {searchArea && !drawing && (
            <button className="btn-secondary" onClick={clearArea}>
              נקה אזור · הצג הכל
            </button>
          )}

          <button className="btn-secondary" onClick={() => setShowControls((v) => !v)}>
            תנאים והעדפות
            {(activeConditions.length > 0 || (options.preferences?.length ?? 0) > 0) && (
              <span className="text-warn">
                {" "}· {activeConditions.length + (options.preferences?.length ?? 0)}
              </span>
            )}
          </button>

          <span className="text-muted" style={{ fontSize: ".88rem" }}>
            {drawing
              ? liveArea === null
                ? "לחיצה מוסיפה קודקוד · לחיצה כפולה או Enter לסיום · Escape לביטול"
                : `${liveArea.points} קודקודים · ${dunam(liveArea.sqm)}`
              : searchArea
                ? "התוצאות מוגבלות לאזור המסומן על המפה"
                : "מוצגים כל המועמדים בעיר"}
          </span>

          {overLimit && (
            <span className="text-bad" style={{ fontWeight: 600, fontSize: ".88rem" }}>
              מעל מגבלת {MAX_AREA_SQM / 1000} הדונם — השרת ידחה
            </span>
          )}
        </div>
      </div>

      {showControls && (
        <div style={{ marginBottom: "1rem" }}>
          <SearchControls
            value={options}
            onChange={setOptions}
            onApply={() => searchArea && runSearch(searchArea, options)}
            disabled={!searchArea || loading}
          />
          {!searchArea && (
            <p className="text-warn" style={{ fontSize: ".84rem", margin: ".5rem 0 0" }}>
              יש לצייר אזור חיפוש כדי להחיל את התנאים.
            </p>
          )}
        </div>
      )}

      <div className="card" style={{ marginBottom: "1.2rem", padding: 0, overflow: "hidden" }}>
        <OpportunityMap
          candidates={candidates}
          drawing={drawing}
          searchArea={searchArea}
          onPolygon={onPolygon}
          onCancelDraw={() => { setDrawing(false); setLiveArea(null); }}
          onDrawProgress={(points, sqm) => setLiveArea({ points, sqm })}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>

      {error && (
        <div className="card tone-bad" style={{ marginBottom: "1rem", display: "flex", gap: ".8rem",
                                       alignItems: "center", flexWrap: "wrap" }}>
          <strong className="text-bad">{error}</strong>
          {retryable && (
            <button className="btn-sm" onClick={() => deliver(retryable)} disabled={delivering !== null}>
              נסה שוב · {retryable.address}
            </button>
          )}
        </div>
      )}

      <div className="card">
        <p className="text-muted" style={{ margin: "0 0 .8rem", fontSize: ".9rem" }}>
          {loading ? "טוען…" : `${candidates.length} מועמדים`}
          {activeConditions.length > 0 && (
            <span> · תנאי חובה: {activeConditions.join(" · ")}</span>
          )}
        </p>
        <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>כתובת</th>
              <th>גוש / חלקה</th>
              <th>שטח (מ״ר)</th>
              <th>קומות</th>
              <th>מצב</th>
              <th>נימוק הסדר</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {candidates.map((candidate) => (
              <tr
                key={candidate.id}
                onClick={() => setSelectedId(candidate.id)}
                className={candidate.id === selectedId ? "is-selected" : undefined}
                style={{ cursor: "pointer" }}
              >
                <td style={{ fontWeight: 600 }}>{candidate.address}</td>
                <td className="mono" style={{ textAlign: "start" }}>
                  {candidate.block ?? "—"} / {candidate.parcel ?? "—"}
                </td>
                <td className="num">{candidate.area_sqm ?? "—"}</td>
                <td>{floorsText(candidate.assessment)}</td>
                <td>
                  {candidate.assessment ? (
                    <span style={{ display: "inline-flex", flexDirection: "column", gap: ".2rem", alignItems: "flex-start" }}>
                      {assessmentBadge(candidate.assessment.status)}
                      {candidate.assessment.blocking.length > 0 && (
                        <span className="text-muted" style={{ fontSize: ".78rem" }}>
                          ממתין ל{gateText(candidate.assessment.blocking)}
                        </span>
                      )}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="text-muted" style={{ fontSize: ".82rem" }}>
                  {candidate.why_selected ?? "—"}
                </td>
                <td style={{ textAlign: "end" }}>
                  {(() => {
                    // מועמד שאינו במסלול המגרשי ייענה ב-409 בכל מקרה, והלחיצה
                    // בדרך שולחת בקשה לתיק הבניין לחינם. הארכיון הוא המשאב
                    // הרגיש ביותר שיש לנו — לחיצה שידוע שתיכשל לא תיגע בו.
                    const blocked = candidate.assessment?.screenable === false;
                    const owned = deliveredIds.has(candidate.id);
                    // ‏684 מ-699 יגררו שליפת תיק חיה, שלוקחת עד 20 שניות.
                    // כפתור שכתוב עליו ״מוסר…״ ואינו זז נראה תקוע; כאן
                    // כתוב מה באמת קורה.
                    const willFetch = candidate.assessment?.deliverable === false;
                    if (owned) {
                      return (
                        <Link href={`/app/dossier/${candidate.id}`} className="text-link" style={{ fontSize: ".82rem" }}>
                          פתח תיק ←
                        </Link>
                      );
                    }
                    // ‏C14 · המצב נאמר **לפני** הלחיצה, ולא רק על הכפתור בזמנה.
                    // באזור ההדגמה שלוש השורות הראשונות אינן מוכנות, ו״מסור לי״
                    // נראה אצלן בדיוק כמו אצל חלקה שהתיק שלה כבר שמור — לחיצה
                    // בטעות הייתה שולפת תיק מהארכיון באמצע ההדגמה.
                    const readiness = blocked ? null
                      : willFetch
                        ? { text: "ישלוף תיק בניין · עד 20 שניות", cls: "text-warn" }
                        : { text: "מוכן למסירה מיידית", cls: "text-ok" };
                    return (
                      <div style={{ display: "inline-flex", flexDirection: "column",
                                    alignItems: "flex-end", gap: ".2rem" }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); deliver(candidate); }}
                          disabled={delivering !== null || owned || blocked}
                          title={blocked ? "אינו במסלול המגרשי — אינו נמסר"
                            : willFetch ? "תיק הבניין ייושלף מהארכיון — עד 20 שניות"
                            : undefined}
                          className="btn-sm"
                        >
                          {blocked ? "לא במסלול"
                            : delivering === candidate.id
                              ? (willFetch ? "שולף תיק בניין…" : "מוסר…")
                              : "מסור לי"}
                        </button>
                        {readiness && (
                          <span className={readiness.cls} style={{ fontSize: ".72rem",
                                         fontWeight: 600, whiteSpace: "nowrap" }}>
                            {readiness.text}
                          </span>
                        )}
                      </div>
                    );
                  })()}
                </td>
              </tr>
            ))}
            {!loading && candidates.length === 0 && !error && (
              <tr>
                <td colSpan={7} className="text-muted">
                  אין מועמדים באזור שסומן.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>
      </>
      )}
    </AppShell>
  );
}
