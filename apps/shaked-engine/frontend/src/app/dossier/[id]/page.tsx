"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { use } from "react";
import { ApiError, downloadDossier, getDossier,
         type Betterment, type Dossier, type EvidenceRow, type Gate } from "@/lib/api";
import {
  ASSUMPTION_STATUS, GATE_STATUS,
} from "@/lib/labels";

const CITY = "herzliya";

// ‏`-0 ₪` על שורה שהיא אפס נראה כמו באג. אפס הוא אפס, וסימן המינוס
// שייך לסכום ולא לעיצוב.
const ils = (n: number) =>
  Math.round(n) === 0 ? "0 ₪" : `${Math.round(n).toLocaleString("he-IL")} ₪`;
const sqm = (n: number) => `${Math.round(n).toLocaleString("he-IL")} מ״ר`;
const date = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("he-IL", { day: "numeric", month: "short", year: "numeric" }) : "—";

function Pill({ text, colour, background }: { text: string; colour: string; background: string }) {
  return (
    <span style={{ background, color: colour, fontWeight: 600, fontSize: ".78rem",
                   padding: ".15rem .5rem", borderRadius: 999, whiteSpace: "nowrap" }}>
      {text}
    </span>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="card" style={{ marginBottom: "1.1rem" }}>
      <h2 style={{ margin: "0 0 .15rem", fontSize: "1.05rem" }}>{title}</h2>
      {note && <p style={{ margin: "0 0 .8rem", color: "#6b655c", fontSize: ".84rem" }}>{note}</p>}
      {children}
    </section>
  );
}

/** שער אחד בשרשרת, עם הסעיף שאפשר לפתוח ולבדוק אותנו לפיו. */
function GateRow({ gate }: { gate: Gate }) {
  const s = GATE_STATUS[gate.status] ?? { label: gate.status, colour: "#5c5750", background: "#f0efec" };
  return (
    <tr>
      <td style={{ width: "6.5rem" }}><Pill text={s.label} {...s} /></td>
      <td style={{ fontWeight: 600 }}>{gate.label}</td>
      <td style={{ color: "#4a4741" }}>{gate.detail || "—"}</td>
      <td style={{ width: "5rem", whiteSpace: "nowrap" }}>
        {gate.source_url ? (
          <a href={gate.source_url} target="_blank" rel="noreferrer"
             style={{ color: "#1d4e89", fontSize: ".8rem" }}>
            {gate.page ? `עמ׳ ${gate.page}` : "מקור"}
          </a>
        ) : "—"}
      </td>
    </tr>
  );
}

function EvidenceTable({ rows }: { rows: EvidenceRow[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>שדה</th><th>ערך</th><th>ודאות</th><th>מכריע?</th><th>נשלף</th><th>מקור</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.field}>
            {/* התווית מגיעה מהשרת — מקור אמת אחד ל-PDF, ל-Excel ולמסך.
                המפה המקומית הוסרה: ״גיבוי״ שאיש אינו רואה כשהוא נכנס
                לפעולה אינו גיבוי אלא באג שקט. אם השרת לא שלח תווית,
                בדיקת `test_labels.py` כבר נפלה. */}
            <td style={{ fontWeight: 600 }}>{r.label}</td>
            <td>{r.value === null || r.value === undefined ? "—"
              : typeof r.value === "boolean" ? (r.value ? "כן" : "לא")
              : typeof r.value === "number" ? r.value.toLocaleString("he-IL")
              : String(r.value)}</td>
            <td>{r.certainty_label}</td>
            <td style={{ color: r.decides ? "#1f5f55" : "#8a6100", fontWeight: 600 }}>
              {r.decides ? "כן" : "לא"}
            </td>
            <td style={{ whiteSpace: "nowrap" }}>{date(r.retrieved_at)}</td>
            <td>
              {r.source_url ? (
                <a href={r.source_url} target="_blank" rel="noreferrer"
                   style={{ color: "#1d4e89", fontSize: ".8rem" }} title={r.location ?? undefined}>
                  {r.location ? r.location.slice(0, 34) : "מקור"}
                </a>
              ) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const BETTERMENT_COLOUR: Record<Betterment["category"], string> = {
  resilient: "#1f5f55", marginal: "#8a6100", no_threshold: "#a8321e",
  // ״לא דורג״ אינו ״עמיד״ — בלי צבע שאומר משהו.
  unrated: "#5c5750",
};

/** ‏C14 · ההיטל כתקרה ולא כ-0 ₪.
 *
 *  ההשבחה אינה ידועה, והתרחיש מחושב בלעדיה. ״היטל השבחה 0 ₪״ אמר ליזם
 *  שאין היטל; מה שאנחנו באמת יודעים הוא עד כמה הרווח סופג אותו. */
function BettermentBlock({ b }: { b: Betterment }) {
  const { levy } = b;
  return (
    <div style={{ marginTop: "1rem", paddingTop: ".9rem", borderTop: "1px solid #eee" }}>
      <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginBottom: ".5rem" }}>
        <div>
          <div style={{ color: "#6b655c", fontSize: ".8rem" }}>
            תקרת היטל ההשבחה · {Math.round(levy.rate * 100)}% מההשבחה
          </div>
          <strong style={{ fontSize: "1.3rem", color: BETTERMENT_COLOUR[b.category] }}>
            {levy.viable_up_to_ils != null ? `עד ${ils(levy.viable_up_to_ils)}` : "אין תקרה"}
          </strong>
        </div>
        {b.breakeven_land_value_per_right_ils != null && (
          <div>
            <div style={{ color: "#6b655c", fontSize: ".8rem" }}>שווי מ״ר זכויות שבו הרווח יורד למזערי</div>
            <strong style={{ fontSize: "1.3rem" }}>{ils(b.breakeven_land_value_per_right_ils)}</strong>
          </div>
        )}
        {levy.low_ils != null && levy.high_ils != null && (
          <div>
            <div style={{ color: "#6b655c", fontSize: ".8rem" }}>אומדן ההיטל</div>
            <strong style={{ fontSize: "1.3rem" }}>{ils(levy.low_ils)}–{ils(levy.high_ils)}</strong>
          </div>
        )}
      </div>
      <p style={{ margin: ".2rem 0", fontWeight: 600, color: BETTERMENT_COLOUR[b.category], fontSize: ".88rem" }}>
        {b.category_label}
      </p>
      {levy.within_range === false && (
        <p style={{ margin: ".2rem 0", fontWeight: 600, color: "#a8321e", fontSize: ".88rem" }}>
          הקצה העליון של אומדן ההיטל גבוה מהתקרה.
        </p>
      )}
      <p style={{ margin: ".2rem 0", color: "#6b655c", fontSize: ".82rem" }}>{b.note}</p>
      {b.estimate_withheld_because && (
        <p style={{ margin: ".2rem 0", color: "#6b655c", fontSize: ".82rem" }}>
          אין אומדן להיטל: {b.estimate_withheld_because}
        </p>
      )}
      {b.rests_on_unresolved_inputs.length > 0 && (
        <p style={{ margin: ".2rem 0", color: "#8a6100", fontSize: ".82rem" }}>
          התקרה זזה עם {b.rests_on_unresolved_inputs.join(" ועם ")}
          {b.rests_on_unresolved_inputs.length === 1 ? ", שעדיין אינו מוכרע." : ", שעדיין אינם מוכרעים."}
        </p>
      )}
    </div>
  );
}

export default function DossierPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [d, setD] = useState<Dossier | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function download(fmt: "pdf" | "xlsx") {
    setDownloading(fmt);
    setDownloadError(null);
    try {
      await downloadDossier(CITY, id, fmt);
    } catch (e) {
      setDownloadError(e instanceof ApiError ? e.detail : "ההורדה נכשלה.");
    } finally {
      setDownloading(null);
    }
  }

  useEffect(() => {
    getDossier(CITY, id)
      .then(setD)
      .catch((e) => {
        // ‏401 = צריך להתחבר, לא תקלה להציג.
        if (e instanceof ApiError && e.status === 401) { router.replace("/login"); return; }
        setError(e instanceof ApiError && e.status === 404
          ? "התיק אינו במאגר החברה."
          : e instanceof ApiError ? e.detail : "לא ניתן לטעון את התיק.");
      });
  }, [id, router]);

  if (error) {
    return (
      <main className="page">
        <div className="card"><strong style={{ color: "#a8321e" }}>{error}</strong></div>
        <p style={{ marginTop: "1rem" }}><Link href="/dashboard">← חזרה למסך החיפוש</Link></p>
      </main>
    );
  }
  if (!d) return <main className="page"><p>טוען…</p></main>;

  const f = d.rights.floors;
  const floorsText = f.low === null ? "—"
    : f.high !== null && f.high !== f.low ? `${f.low}–${f.high}` : String(f.low);
  const s = d.economics.scenario as Record<string, number> | null;

  return (
    <main className="page" style={{ maxWidth: 1000 }}>
      <p style={{ margin: "0 0 .6rem" }}>
        <Link href="/dashboard" style={{ color: "#6b655c", fontSize: ".85rem" }}>← חזרה</Link>
      </p>

      <header style={{ marginBottom: "1.1rem", display: "flex", gap: "1rem",
                       alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: "16rem" }}>
        <h1 style={{ margin: 0 }}>{d.identity.address}</h1>
        <p style={{ margin: ".2rem 0 0", color: "#6b655c" }}>
          גוש {d.identity.block ?? "—"} · חלקה {d.identity.parcel ?? "—"}
          {d.identity.area_sqm ? ` · ${sqm(d.identity.area_sqm)}` : ""}
          {d.identity.existing_units ? ` · ${d.identity.existing_units} דירות קיימות` : ""}
          {" · נמסר ב-"}{date(d.delivery.delivered_at)}
        </p>
        </div>
        <div style={{ display: "flex", gap: ".45rem", flexWrap: "wrap" }}>
          <button onClick={() => download("pdf")} disabled={downloading !== null}
                  style={{ padding: ".45rem .9rem", fontSize: ".85rem" }}>
            {downloading === "pdf" ? "מפיק…" : "הורד PDF"}
          </button>
          <button onClick={() => download("xlsx")} disabled={downloading !== null}
                  style={{ padding: ".45rem .9rem", fontSize: ".85rem", background: "#1d4e89" }}>
            {downloading === "xlsx" ? "מפיק…" : "הורד Excel"}
          </button>
        </div>
      </header>

      {downloadError && (
        <div className="card" style={{ marginBottom: "1rem", borderColor: "#e6c9c2",
                                       background: "#fdf6f4" }}>
          <strong style={{ color: "#a8321e" }}>{downloadError}</strong>
        </div>
      )}

      <Section
        title="שרשרת הזכויות"
        note="כל שער עם הסעיף שאפשר לפתוח ולבדוק אותנו לפיו. ״לא ידוע״ אינו ״עבר״."
      >
        <div style={{ overflowX: "auto" }}>
          <table><tbody>{d.rights.checks.map((g) => <GateRow key={g.id} gate={g} />)}</tbody></table>
        </div>

        <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginTop: "1rem",
                      paddingTop: ".9rem", borderTop: "1px solid #eee" }}>
          <div>
            <div style={{ color: "#6b655c", fontSize: ".8rem" }}>קומות מותרות</div>
            <strong style={{ fontSize: "1.3rem" }}>{floorsText}</strong>
            <span style={{ color: "#8a6100", fontSize: ".8rem" }}>
              {f.case_by_case ? " · בחינה נקודתית" : f.certain ? "" : " · דורש מדידה"}
            </span>
          </div>
          <div>
            <div style={{ color: "#6b655c", fontSize: ".8rem" }}>תקרת 400%</div>
            <strong style={{ fontSize: "1.3rem" }}>
              {d.rights.cap_400_sqm ? sqm(d.rights.cap_400_sqm) : "—"}
            </strong>
            {d.rights.cap_400_certainty === "estimate" && (
              <span style={{ color: "#8a6100", fontSize: ".8rem" }}> · על אומדן</span>
            )}
          </div>
          {d.rights.unit_mix && (
            <div>
              <div style={{ color: "#6b655c", fontSize: ".8rem" }}>יחידות אחרי</div>
              <strong style={{ fontSize: "1.3rem" }}>
                {d.rights.unit_mix.units_min}–{d.rights.unit_mix.units_max}
              </strong>
            </div>
          )}
          {d.rights.parking?.spaces != null && (
            <div>
              <div style={{ color: "#6b655c", fontSize: ".8rem" }}>חניות</div>
              <strong style={{ fontSize: "1.3rem" }}>{String(d.rights.parking.spaces)}</strong>
            </div>
          )}
        </div>

        {d.rights.cap_400_basis && (
          <p style={{ margin: ".8rem 0 0", color: "#6b655c", fontSize: ".82rem" }}>
            {d.rights.cap_400_basis}
          </p>
        )}
        {d.rights.notes.map((n) => (
          <p key={n} style={{ margin: ".3rem 0 0", color: "#6b655c", fontSize: ".82rem" }}>{n}</p>
        ))}
      </Section>

      <Section
        title="מאיפה הגיע כל מספר"
        note="מקור, מועד וודאות לכל שדה מהותי. ״מכריע״ פירושו שהתצפית רשאית להכריע שער — ודאות, מקור, מיקום וגיל, כולם יחד."
      >
        <div style={{ overflowX: "auto" }}><EvidenceTable rows={d.evidence} /></div>
      </Section>

      <Section title="תרחיש כלכלי" note={d.economics.disclaimer}>
        {s ? (
          <>
            <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <div>
                <div style={{ color: "#6b655c", fontSize: ".8rem" }}>
                  רווח צפוי{d.economics.betterment ? " · לפני היטל השבחה" : ""}
                </div>
                <strong style={{ fontSize: "1.3rem" }}>{ils(s.projected_profit_ils)}</strong>
              </div>
              <div>
                <div style={{ color: "#6b655c", fontSize: ".8rem" }}>רווח על העלות</div>
                <strong style={{ fontSize: "1.3rem",
                                 color: s.meets_developer_target ? "#1f5f55" : "#8a6100" }}>
                  {Math.round(s.profit_margin_on_cost_ratio * 100)}%
                </strong>
              </div>
              <div>
                {/* ‏C14 · היה ״שטח נמכר״, והמספר הוא השטח שנשאר ליזם אחרי הדיירים.
                    באקסל ״שטח נמכר (עיקרי)״ הוא כל השטח העיקרי — שם אחד, שני
                    מספרים, בדיוק ברגע שהיזם פותח את האקסל מול המסך. */}
                <div style={{ color: "#6b655c", fontSize: ".8rem" }}>שטח ליזם</div>
                <strong style={{ fontSize: "1.3rem" }}>{sqm(s.developer_allocation_sqm)}</strong>
              </div>
            </div>

            {/* ‏E1 · מעל או מתחת ל-16%, במילים ולא רק בצבע. המשפט מהשרת, כמו ב-PDF ובאקסל. */}
            {d.economics.profit_verdict && (
              <p style={{ margin: "-.4rem 0 1rem", fontWeight: 600, fontSize: ".9rem",
                          color: s.meets_developer_target ? "#1f5f55" : "#8a6100" }}>
                {d.economics.profit_verdict}
              </p>
            )}

            {/* ‏C14 · הסייג צמוד למספר שהוא מסייג. הנוסח מהשרת, כמו
                ‏`not_delivered_reason` — אותו משפט במסך, ב-PDF ובאקסל. */}
            {d.economics.caveats.length > 0 && (
              <div style={{ marginBottom: "1rem", padding: ".7rem .9rem", borderRadius: 8,
                            background: "#fbf4e4", color: "#6b4c00", fontSize: ".86rem" }}>
                <strong style={{ display: "block", marginBottom: ".3rem", color: "#8a6100" }}>
                  על מה הרווח נשען
                </strong>
                <ul style={{ margin: 0, paddingInlineStart: "1.1rem" }}>
                  {d.economics.caveats.map((c) => (
                    <li key={c.id} style={{ marginBottom: ".2rem" }}>{c.text}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* ‏B15 · התמהיל שהיזם חישב. המשפט מהשרת, כמו ב-PDF ובאקסל,
                והרווח שמעליו אינו זז בגללו (בועז, 15.09). */}
            <div style={{ marginBottom: "1rem", padding: ".7rem .9rem", borderRadius: 8,
                          background: "#eef3f8", color: "#1d3f66", fontSize: ".86rem" }}>
              {d.economics.unit_mix?.summary ? (
                <>
                  {d.economics.unit_mix.summary}{" "}
                  <Link href={`/dossier/${id}/mix`}>שנה את התמורה ←</Link>
                </>
              ) : (
                <>
                  תמהיל הדירות עוד לא חושב.{" "}
                  <Link href={`/dossier/${id}/mix`}>חשב תמהיל ורווחיות ←</Link>
                </>
              )}
            </div>

            <table>
              <tbody>
                {([
                  ["הכנסות (נטו ממע״מ)", s.total_revenue_ils],
                  ["קרקע — פיצוי הדיירים", -s.land_cost_ils],
                  ["בנייה מעל הקרקע", -s.total_construction_cost_ils],
                  ["חניון תת-קרקעי", -s.total_underground_cost_ils],
                  ["עלויות רכות", -s.total_soft_cost_ils],
                  ["הריסה", -s.total_demolition_cost_ils],
                  ["שכירות והובלות לדיירים", -s.total_tenant_cost_ils],
                  ["שיווק ותיווך", -s.total_marketing_ils],
                  ["ערבויות וביטוח", -s.total_guarantees_ils],
                  ["מימון", -s.total_finance_ils],
                  // ‏0 ₪ כאן אינו ״אין היטל״ אלא ״ההשבחה אינה ידועה״. התקרה מתחת.
                  ...(d.economics.betterment ? [] : [["היטל השבחה", -s.betterment_levy_ils]]),
                ] as [string, number][]).map(([name, value]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td style={{ textAlign: "end", fontVariantNumeric: "tabular-nums",
                                 color: value < 0 ? "#a8321e" : "#1f5f55" }}>
                      {ils(value)}
                    </td>
                  </tr>
                ))}
                {/* ‏B13 · שורת ההיטל נכתבת פעם אחת בשרת, וה-PDF והאקסל מדפיסים
                    אותה כמו שהיא. נוסח מקומי כאן היה נפרד מהם בשקט. */}
                {d.economics.betterment && (
                  <tr>
                    <td colSpan={2} style={{ color: "#8a6100", fontWeight: 600 }}>
                      {d.economics.betterment.summary}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            {d.economics.betterment && <BettermentBlock b={d.economics.betterment} />}
          </>
        ) : (
          <p style={{ color: "#8a6100" }}>{d.economics.why ?? "לא חושב תרחיש."}</p>
        )}

        {/* המשפט נכתב בשרת ולא כאן. הוא הופיע קודם בשלושה נוסחים —
            במסך, ב-PDF וב-Excel — וכל שלושתם צירפו מזהי קוד. */}
        {!d.economics.is_deliverable && d.economics.not_delivered_reason && (
          <div style={{ marginTop: "1rem", padding: ".7rem .9rem", borderRadius: 8,
                        background: "#fbf4e4", color: "#8a6100" }}>
            {d.economics.not_delivered_reason}
          </div>
        )}

        <details style={{ marginTop: "1rem" }}>
          <summary style={{ cursor: "pointer", color: "#1d4e89", fontSize: ".88rem" }}>
            כל ההנחות · גרסה {d.economics.assumptions_version}
          </summary>
          <table style={{ marginTop: ".6rem" }}>
            <tbody>
              {Object.entries(d.economics.assumptions).map(([k, a]) => {
                const st = ASSUMPTION_STATUS[a.status] ?? { label: a.status, colour: "#5c5750" };
                return (
                  <tr key={k}>
                    <td>{a.label}</td>
                    <td style={{ fontVariantNumeric: "tabular-nums" }}>
                      {a.value.toLocaleString("he-IL")} <span style={{ color: "#6b655c" }}>{a.unit}</span>
                    </td>
                    <td style={{ color: st.colour, fontWeight: 600 }}>{st.label}</td>
                    <td style={{ color: "#6b655c", fontSize: ".8rem" }}>{a.source ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      </Section>

      <Section title="פערים" note={d.gaps.note}>
        {[
          ["שערים שלא נענו", d.gaps.unknown_gates.map((g) => g.label)],
          ["אין להם מקור פתוח", d.gaps.unobtainable.map((x) => x.label)],
          ["נבדק ולא נמצא", d.gaps.checked_and_not_found.map((x) => x.label)],
          ["מעולם לא נשאל", d.gaps.never_asked.map((x) => x.label)],
          ["מקורות שהתיישנו", d.gaps.stale_sources.map((x) => x.label)],
        ].map(([title, items]) => (
          <div key={title as string} style={{ marginBottom: ".55rem" }}>
            <strong style={{ fontSize: ".87rem" }}>{title}: </strong>
            <span style={{ color: (items as string[]).length ? "#4a4741" : "#6b655c", fontSize: ".87rem" }}>
              {(items as string[]).length ? (items as string[]).join(" · ") : "אין"}
            </span>
          </div>
        ))}
      </Section>

      <footer style={{ color: "#6b655c", fontSize: ".8rem", paddingBottom: "2rem" }}>
        כללים {d.versions.rules_version} · נתונים {d.versions.data_version || "—"} ·
        תבנית {d.versions.template_version}
      </footer>
    </main>
  );
}
