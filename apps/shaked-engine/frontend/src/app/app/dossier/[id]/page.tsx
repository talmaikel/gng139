"use client";

import { Accordion, ActionIcon, Alert, Anchor, Button, Group, List, Paper, Popover, Table, Text } from "@mantine/core";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { use } from "react";
import { ApiError, downloadDossier, getDossier, getUnitReviewCounts,
         type Betterment, type Dossier, type EvidenceRow, type Gate, type TermId } from "@/lib/api";
import { fmtDate as date, ils, ilsApprox, sqm } from "@/lib/format";
import type { Tone } from "@/lib/labels";
import { IconFile, IconHelp, IconSheet } from "@/components/brand/icons";
import { assumptionBadge, gateBadge, PageHeader, Section, Stat, StatStrip, StatusBadge } from "@/components/brand/ui";
import { GlossaryContext, Term, WithTerm } from "@/components/Term";
import type { CostRow, LevyExplainParagraph, PolicyArea, PolicyDossier, RightsVerdict, ScenarioCard } from "@/lib/dossier";

const CITY = "herzliya";

/** ‏W4 · סטטוס שער שאינו מסביר את עצמו ← המונח שמסביר אותו. */
const GATE_TERM: Partial<Record<string, TermId>> = {
  routed: "routed", undefined: "policy_silent", needs_measurement: "needs_measurement",
};

/** שער אחד מתנאי חלופת שקד, עם הסעיף שאפשר לפתוח ולבדוק אותנו לפיו. */
function GateRow({ gate }: { gate: Gate }) {
  const term = GATE_TERM[gate.status];
  return (
    <Table.Tr>
      <Table.Td w="7rem" style={{ whiteSpace: "nowrap" }}>
        {term ? <WithTerm id={term}>{gateBadge(gate.status)}</WithTerm> : gateBadge(gate.status)}
      </Table.Td>
      <Table.Td fw={600}>{gate.label}</Table.Td>
      <Table.Td c="var(--ink-2)">{gate.detail || "—"}</Table.Td>
      <Table.Td w="5rem" style={{ whiteSpace: "nowrap" }}>
        {gate.source_url ? (
          <Anchor href={gate.source_url} target="_blank" rel="noreferrer" size="sm" c="almond.7">
            {gate.page ? `עמ׳ ${gate.page}` : "מקור"}
          </Anchor>
        ) : "—"}
      </Table.Td>
    </Table.Tr>
  );
}

function EvidenceTable({ rows }: { rows: EvidenceRow[] }) {
  return (
    <Table.ScrollContainer minWidth={720}>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>שדה</Table.Th><Table.Th>ערך</Table.Th>
            <Table.Th><WithTerm id="certainty">ודאות</WithTerm></Table.Th>
            <Table.Th><WithTerm id="deciding">מכריע?</WithTerm></Table.Th>
            <Table.Th>נשלף</Table.Th><Table.Th>מקור</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.field}>
              {/* התווית מגיעה מהשרת — מקור אמת אחד ל-PDF, ל-Excel ולמסך.
                  המפה המקומית הוסרה: ״גיבוי״ שאיש אינו רואה כשהוא נכנס
                  לפעולה אינו גיבוי אלא באג שקט. אם השרת לא שלח תווית,
                  בדיקת `test_labels.py` כבר נפלה. */}
              <Table.Td fw={600}>{r.term ? <WithTerm id={r.term}>{r.label}</WithTerm> : r.label}</Table.Td>
              <Table.Td className="num">{r.value === null || r.value === undefined ? "—"
                : typeof r.value === "boolean" ? (r.value ? "כן" : "לא")
                : typeof r.value === "number" ? r.value.toLocaleString("he-IL")
                : String(r.value)}</Table.Td>
              <Table.Td>{r.certainty_label}</Table.Td>
              <Table.Td><StatusBadge tone={r.decides ? "ok" : "warn"} size="xs">{r.decides ? "כן" : "לא"}</StatusBadge></Table.Td>
              <Table.Td style={{ whiteSpace: "nowrap" }}>{date(r.retrieved_at)}</Table.Td>
              <Table.Td>
                {r.source_url ? (
                  <Anchor href={r.source_url} target="_blank" rel="noreferrer" size="sm" c="almond.7" title={r.location ?? undefined}>
                    {r.location ? r.location.slice(0, 34) : "מקור"}
                  </Anchor>
                ) : "—"}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

const BETTERMENT_TONE: Record<Betterment["category"], Tone> = {
  resilient: "ok", marginal: "warn", no_threshold: "bad",
  // ״לא דורג״ אינו ״עמיד״ — בלי צבע שאומר משהו.
  unrated: "neutral",
};

/** ‏C14 · ההיטל כתקרה ולא כ-0 ₪.
 *
 *  ההשבחה אינה ידועה, והתרחיש מחושב בלעדיה. ״היטל השבחה 0 ₪״ אמר ליזם
 *  שאין היטל; מה שאנחנו באמת יודעים הוא עד כמה הרווח סופג אותו. */
function BettermentBlock({ b }: { b: Betterment }) {
  const { levy } = b;
  const tone = BETTERMENT_TONE[b.category];
  return (
    <div style={{ marginTop: "1rem", paddingTop: ".9rem", borderTop: "1px solid var(--rule-2)" }}>
      <StatStrip cols={{ base: 1, sm: 3 }}>
        <Stat
          label={<WithTerm id="levy_ceiling">{`תקרת היטל ההשבחה · ${Math.round(levy.rate * 100)}% מההשבחה`}</WithTerm>}
          value={levy.viable_up_to_ils != null ? `עד ${ilsApprox(levy.viable_up_to_ils)}` : "אין תקרה"}
          tone={tone}
        />
        {b.breakeven_land_value_per_right_ils != null && (
          <Stat label={<WithTerm id="breakeven_land_value">שווי מ״ר זכויות שבו הרווח יורד למזערי</WithTerm>}
                value={ils(b.breakeven_land_value_per_right_ils)} />
        )}
        {levy.low_ils != null && levy.high_ils != null && (
          <Stat label={<WithTerm id="levy_estimate">אומדן ההיטל</WithTerm>}
                value={`${ilsApprox(levy.low_ils)}–${ilsApprox(levy.high_ils)}`} />
        )}
      </StatStrip>
      <Group gap="xs" mt="sm">
        <Group gap={2} wrap="nowrap" maw="100%">
          <StatusBadge tone={tone}>{b.category_label}</StatusBadge><Term id="levy_category" />
        </Group>
        {levy.within_range === false && (
          <Text size="sm" fw={600} className="text-bad">הקצה העליון של אומדן ההיטל גבוה מהתקרה.</Text>
        )}
      </Group>
      <Text size="sm" c="dimmed" mt={6}>{b.note}</Text>
      {/* ‏W3 · נקודות 9 ו-13: איך מחושבים ההיטל, האומדן, הטווח והתקרה. הפסקאות מהשרת,
          עם המספרים של החלקה — אותו נוסח ב-PDF ובאקסל. */}
      {!!(b as Betterment & { explain?: LevyExplainParagraph[] }).explain?.length && (
        <Accordion variant="contained" mt="sm" radius="sm">
          <Accordion.Item value="levy-explain">
            <Accordion.Control><Text size="sm" fw={600}>איך מחושב היטל ההשבחה</Text></Accordion.Control>
            <Accordion.Panel>
              {(b as Betterment & { explain: LevyExplainParagraph[] }).explain.map((p) => (
                <div key={p.id} style={{ marginBottom: ".6rem" }}>
                  <Text size="sm" fw={600}>{p.title}</Text>
                  <Text size="sm">{p.text}</Text>
                </div>
              ))}
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      )}
      {b.estimate_withheld_because && (
        <Text size="sm" c="dimmed" mt={4}>אין אומדן להיטל: {b.estimate_withheld_because}</Text>
      )}
      {b.rests_on_unresolved_inputs.length > 0 && (
        <Text size="sm" className="text-warn" mt={4}>
          התקרה זזה עם {b.rests_on_unresolved_inputs.join(" ועם ")}
          {b.rests_on_unresolved_inputs.length === 1 ? ", שעדיין אינו מוכרע." : ", שעדיין אינם מוכרעים."}
        </Text>
      )}
    </div>
  );
}

const pct = (x: number | null | undefined, digits = 0) =>
  x == null ? "—" : `${(x * 100).toLocaleString("he-IL", { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
const far = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x).toLocaleString("he-IL")}%`);

/** ‏W1 · 400% הוא תקרה בחוק ולא זכות. מה שנכנס בפועל לפי מדיניות הרצליה, והפער. */
function PolicyAreaBlock({ p }: { p: PolicyArea }) {
  if (!p.base || !p.low || !p.high) {
    return p.why ? (
      <Alert color="almond" mt="md" title="לא חושב שטח לפי מדיניות הרצליה">{p.why}</Alert>
    ) : null;
  }
  const { base, low, high } = p;
  const geometric = p.geometric?.base;
  const range = Math.abs(high.sqm - low.sqm) < 50 ? undefined : `טווח ${sqm(low.sqm)}–${sqm(high.sqm)}`;
  return (
    <div style={{ marginTop: "1rem", paddingTop: ".9rem", borderTop: "1px solid var(--rule-2)" }}>
      <Group gap={4} wrap="nowrap">
        <Text fw={700}>זכויות לפי מדיניות הרצליה מול תקרת 400%</Text>
        <Term id="policy_area" />
      </Group>
      <StatStrip cols={{ base: 2, sm: 4 }}>
        <Stat label={<WithTerm id="cap_400">תקרת 400% · תאורטית</WithTerm>}
              value={p.cap_400_sqm ? sqm(p.cap_400_sqm) : "—"}
              hint={p.cap_400_far_pct ? `${far(p.cap_400_far_pct)} בנייה · פי 4 מהבנוי הקיים` : undefined}
              hintTone="neutral" />
        <Stat label="מקסימום גאומטרי לפי המדיניות" value={geometric ? sqm(geometric.sqm) : "—"}
              hint={geometric ? `${far(geometric.far_pct)} בנייה · לפני מקדם תכנון` : undefined}
              hintTone="neutral" />
        <Stat label={`אומדן שמרני למימוש${p.eta != null ? ` · ${pct(p.eta)}` : ""}`}
              value={sqm(base.sqm)} tone="ok"
              hint={`${far(base.far_pct)} בנייה${range ? ` · ${range}` : ""}`} hintTone="neutral" />
        <Stat label="פער מול התקרה" value={base.gap_sqm != null ? sqm(base.gap_sqm) : "—"}
              hint={base.gap_far_pct != null
                ? `${Math.round(base.gap_far_pct)} נקודות אחוזי בנייה · האומדן מנצל ${pct(base.share_of_cap)} מהתקרה`
                : undefined} />
      </StatStrip>
      <Text size="sm" mt="sm">
        מגרש {p.plot_sqm ? sqm(p.plot_sqm) : "—"} · מעטפת בתוך קווי הבניין{" "}
        {p.envelope_sqm ? sqm(p.envelope_sqm) : "—"} לקומה
        {p.envelope_share_of_plot != null ? ` (${pct(p.envelope_share_of_plot)} מהמגרש)` : ""}
        {p.binding === "cap" ? " · המעטפת גדולה מהתקרה, ולכן התקרה היא המגבלה" : ""}
      </Text>
      {!!p.limits?.length && (
        <>
          <Text size="sm" fw={600} mt="sm">מה מגביל</Text>
          <List size="sm" spacing={2}>{p.limits.map((x) => <List.Item key={x}>{x}</List.Item>)}</List>
        </>
      )}
      {!!p.assumptions?.length && (
        <>
          <Text size="sm" fw={600} mt="sm" c="dimmed">הנחות · אומדן, לא תכנון אדריכלי</Text>
          <List size="sm" spacing={2} c="dimmed">{p.assumptions.map((x) => <List.Item key={x}>{x}</List.Item>)}</List>
        </>
      )}
      {p.sources?.map((src) => (
        <Anchor key={src.url} href={src.url} target="_blank" rel="noreferrer" size="sm" c="almond.7" mt={6} display="inline-block">
          {src.label}
        </Anchor>
      ))}
    </div>
  );
}

/** ‏W4 · נקודה 6: ״?״ ליד שורה בטבלת העלויות — מה השורה, הנוסחה ומאיפה הקלט. בלחיצה, כמו המונחים. */
function RowInfo({ row }: { row: CostRow }) {
  return (
    <Popover width={340} position="bottom" withArrow shadow="md" trapFocus returnFocus>
      <Popover.Target>
        <ActionIcon variant="subtle" color="gray" size={24} my={-4} radius="xl"
                    aria-label={`מה זה: ${row.label}`} style={{ verticalAlign: "middle", flex: "none" }}>
          <IconHelp size={14} />
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown style={{ maxWidth: "calc(100vw - 2rem)" }}>
        <Text size="sm" fw={600}>{row.label}</Text>
        <Text size="sm" mt={4} style={{ lineHeight: 1.55 }}>{row.explain}</Text>
        <Text size="sm" mt={6} className="mono" style={{ lineHeight: 1.55 }}>{row.formula}</Text>
        <Text size="xs" c="dimmed" mt={6} style={{ lineHeight: 1.5 }}>מקור: {row.source}</Text>
      </Popover.Dropdown>
    </Popover>
  );
}

/** ‏W4 · ערך הנחה ביחידה שיזם קורא: שיעור כאחוז, ו-₪ למ״ר במקום ILS/sqm. */
function assumptionValue(a: { value: number; unit: string; unit_label?: string }) {
  if (a.unit === "ratio") return `${(a.value * 100).toLocaleString("he-IL", { maximumFractionDigits: 2 })}%`;
  return `${a.value.toLocaleString("he-IL")} ${a.unit_label ?? a.unit}`;
}

function WithRowInfo({ row }: { row: CostRow }) {
  return <span>{row.label}{"\u00a0"}<RowInfo row={row} /></span>;
}

const VERDICT: Record<RightsVerdict["case"], { title: string; color: string }> = {
  A: { title: "כלכלי לפי מדיניות הרצליה", color: "moss" },
  B: { title: "כלכלי רק עם הגדלת זכויות", color: "almond" },
  C: { title: "לא כלכלי גם בתקרת 400%", color: "brick" },
  D: { title: "לא חושב שטח לפי המדיניות", color: "gray" },
};

/** ‏W2 · כלכלי לפי המדיניות? ואם לא — כמה זכויות צריך לבקש. המשפט מהשרת. */
function RightsVerdictAlert({ v }: { v: RightsVerdict }) {
  return (
    <Alert color={VERDICT[v.case].color} title={VERDICT[v.case].title} mt="md">
      <Text size="sm">{v.text}</Text>
      {v.case === "B" && v.required_area_sqm != null && (
        <StatStrip cols={{ base: 1, sm: 3 }}>
          <Stat label="שטח נדרש לכדאיות" value={sqm(v.required_area_sqm)}
                hint={v.required_far_pct != null ? `${far(v.required_far_pct)} בנייה` : undefined} hintTone="neutral" />
          <Stat label="תוספת מעל המדיניות" value={v.required_addition_sqm != null ? sqm(v.required_addition_sqm) : "—"}
                hint={v.addition_far_pct != null ? `${Math.round(v.addition_far_pct)} נקודות אחוזי בנייה` : undefined} />
          <Stat label="מתקרת 400%" value={pct(v.required_share_of_cap)} />
        </StatStrip>
      )}
    </Alert>
  );
}

/** ‏W2 · אותן שורות כמו בגיליון ״מדיניות מול 400%״ וב-PDF. */
function ComparisonTable({ policy, cap }: { policy: ScenarioCard; cap: ScenarioCard }) {
  const rows: [string, (c: ScenarioCard) => string][] = [
    ["שטח לבנייה", (c) => sqm(c.area_sqm)],
    ["אחוזי בנייה מהמגרש", (c) => far(c.far_pct)],
    ["שטח ליזם", (c) => sqm(c.developer_allocation_sqm)],
    ["רווח לפני היטל", (c) => ilsApprox(c.profit_before_levy_ils)],
    ["תקרת היטל שמשאירה רווח מזערי", (c) => (c.levy_ceiling_ils != null ? ilsApprox(c.levy_ceiling_ils) : "אין")],
    ["אומדן היטל השבחה", (c) => (c.levy_estimate_ils != null ? ilsApprox(c.levy_estimate_ils) : "—")],
    ["רווח אחרי אומדן היטל", (c) => (c.profit_after_levy_ils != null ? ilsApprox(c.profit_after_levy_ils) : "—")],
    ["רווח על העלות, לפני היטל", (c) => pct(c.margin_before_levy, 1)],
    ["רווח על העלות, אחרי אומדן היטל", (c) => pct(c.margin_after_levy, 1)],
  ];
  return (
    <Table.ScrollContainer minWidth={460} mt="md">
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>השוואה</Table.Th>
            <Table.Th ta="end">לפי המדיניות</Table.Th>
            <Table.Th ta="end">תקרת 400% · תאורטית</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map(([label, f]) => (
            <Table.Tr key={label}>
              <Table.Td>{label}</Table.Td>
              <Table.Td ta="end" className="num" fw={600}>{f(policy)}</Table.Td>
              <Table.Td ta="end" className="num" c="dimmed">{f(cap)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

export default function DossierPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [d, setD] = useState<PolicyDossier | null>(null);
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

  // ‏C15 · מסך האישור (PR #17) קיים, ועד היום לא היה מקושר מהתיק עם מה שמחכה בו.
  const [unitReview, setUnitReview] = useState<{ total: number; pending: number } | null>(null);
  useEffect(() => {
    getUnitReviewCounts(id).then(setUnitReview).catch(() => setUnitReview(null));
  }, [id]);

  useEffect(() => {
    getDossier(CITY, id)
      .then((x) => setD(x as PolicyDossier))
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
      <>
        <Alert color="brick" title={error} />
        <p style={{ marginTop: "1rem" }}><Link href="/app" className="text-link">← חזרה למסך החיפוש</Link></p>
      </>
    );
  }
  if (!d) return <Text c="dimmed">טוען…</Text>;

  const f = d.rights.floors;
  const floorsText = f.low === null ? "—"
    : f.high !== null && f.high !== f.low ? `${f.low}–${f.high}` : String(f.low);
  const s = d.economics.scenario as Record<string, number> | null;
  const econ = d.economics;
  const after = econ.after_levy ?? null;

  return (
    <GlossaryContext.Provider value={d.glossary ?? {}}>
      <PageHeader
        back={{ href: "/app", label: "חזרה" }}
        eyebrow="תיק הזדמנות · הרצליה"
        title={d.identity.address}
        meta={
          <>
            גוש <span className="mono">{d.identity.block ?? "—"}</span> · חלקה <span className="mono">{d.identity.parcel ?? "—"}</span>
            {d.identity.area_sqm ? ` · ${sqm(d.identity.area_sqm)}` : ""}
            {d.identity.existing_units ? ` · ${d.identity.existing_units} דירות קיימות` : ""}
            {" · נמסר ב-"}{date(d.delivery.delivered_at)}
          </>
        }
        actions={
          <>
            <Button variant="default" leftSection={<IconFile size={15} />} loading={downloading === "pdf"}
                    disabled={downloading !== null} onClick={() => download("pdf")}>
              PDF
            </Button>
            <Button leftSection={<IconSheet size={15} />} loading={downloading === "xlsx"}
                    disabled={downloading !== null} onClick={() => download("xlsx")}>
              Excel
            </Button>
          </>
        }
      />

      {downloadError && <Alert color="brick" mb="md">{downloadError}</Alert>}

      <Section
        id="rights"
        title="עמידה בתנאי חלופת שקד"
        help={<Term id="shaked_conditions" />}
        note="כל שער עם הסעיף שאפשר לפתוח ולבדוק אותנו לפיו. ״לא ידוע״ אינו ״עבר״."
      >
        <Table.ScrollContainer minWidth={560}>
          <Table>
            <Table.Tbody>{d.rights.checks.map((g) => <GateRow key={g.id} gate={g} />)}</Table.Tbody>
          </Table>
        </Table.ScrollContainer>

        <div style={{ paddingTop: ".4rem", borderTop: "1px solid var(--rule-2)" }}>
          <StatStrip>
            <Stat
              label={<WithTerm id="certain_floors">קומות מותרות</WithTerm>}
              value={floorsText}
              hint={f.case_by_case ? "בחינה נקודתית" : f.certain ? undefined : "דורש מדידה"}
            />
            <Stat
              label={<WithTerm id="cap_400">תקרת 400% · תאורטית</WithTerm>}
              value={d.rights.cap_400_sqm ? sqm(d.rights.cap_400_sqm) : "—"}
              hint={d.rights.cap_400_certainty === "estimate" ? "על אומדן · תקרה בחוק, לא זכות" : "תקרה בחוק, לא זכות"}
            />
            {d.rights.unit_mix && (
              <Stat label="יחידות אחרי" value={`${d.rights.unit_mix.units_min}–${d.rights.unit_mix.units_max}`} />
            )}
            {d.rights.parking?.spaces != null && (
              <Stat label="חניות" value={String(d.rights.parking.spaces)} />
            )}
          </StatStrip>
        </div>

        {d.rights.policy_area && <PolicyAreaBlock p={d.rights.policy_area} />}

        {d.rights.cap_400_basis && <Text size="sm" c="dimmed" mt="md">{d.rights.cap_400_basis}</Text>}
        {d.rights.notes.map((n) => <Text key={n} size="sm" c="dimmed" mt={4}>{n}</Text>)}
      </Section>

      <Section
        id="evidence"
        title="מאיפה הגיע כל מספר"
        note="מקור, מועד וודאות לכל שדה מהותי. ״מכריע״ פירושו שהערך רשאי להכריע שער: ודאות רשמית, נגזרת או מאומתת ידנית, מקור עם כתובת ומועד שליפה, מיקום בתוך המקור, ושליפה שלא התיישנה — כולם יחד."
      >
        <EvidenceTable rows={d.evidence} />
      </Section>

      <Section id="economics" title="תרחיש כלכלי" note={d.economics.disclaimer}>
        {s ? (
          <>
            {/* ‏W2 · הרווח מחושב על השטח שמותר לפי המדיניות, ולא על תקרת 400%. */}
            {econ.area_basis === "policy" && econ.buildable_area_sqm != null && (
              <Text size="sm" c="dimmed">
                מחושב על {sqm(econ.buildable_area_sqm)} — אומדן תכנוני שמרני לפי מדיניות הרצליה. המקסימום הגאומטרי ותקרת 400% מוצגים להשוואה בלבד.
              </Text>
            )}
            <StatStrip cols={{ base: 1, sm: after ? 4 : 3 }}>
              <Stat
                label={after
                  ? <WithTerm id="profit_after_levy">רווח יזמי אחרי היטל השבחה (אומדן)</WithTerm>
                  : `רווח צפוי${d.economics.betterment ? " · לפני היטל השבחה" : ""}`}
                value={ilsApprox(s.projected_profit_ils)}
                tone={s.projected_profit_ils < 0 ? "bad" : undefined}
              />
              <Stat
                label={<WithTerm id="profit_on_cost">{after ? "רווח על העלות · אחרי היטל" : "רווח על העלות"}</WithTerm>}
                value={pct(s.profit_margin_on_cost_ratio)}
                tone={s.meets_developer_target ? "ok" : "warn"}
                hint={after ? `טווח ${pct(after.margin_low)}–${pct(after.margin_high)} לפי טווח ההיטל` : undefined}
                hintTone="neutral"
              />
              {after && econ.before_levy && (
                <Stat label="רווח לפני היטל" value={ilsApprox(econ.before_levy.profit_ils)}
                      hint={pct(econ.before_levy.margin, 1)} hintTone="neutral" />
              )}
              {/* ‏C14 · היה ״שטח נמכר״, והמספר הוא השטח שנשאר ליזם אחרי הדיירים.
                  באקסל ״שטח נמכר (עיקרי)״ הוא כל השטח העיקרי — שם אחד, שני
                  מספרים, בדיוק ברגע שהיזם פותח את האקסל מול המסך. */}
              <Stat label={<WithTerm id="developer_area">שטח ליזם</WithTerm>} value={sqm(s.developer_allocation_sqm)} />
            </StatStrip>

            {/* ‏E1 · מעל או מתחת ל-16%, במילים ולא רק בצבע. המשפט מהשרת, כמו ב-PDF ובאקסל. */}
            {d.economics.profit_verdict && (
              <Text size="sm" fw={600} mt="sm" className={s.meets_developer_target ? "text-ok" : "text-warn"}>
                {d.economics.profit_verdict}
              </Text>
            )}

            {econ.rights_verdict && <RightsVerdictAlert v={econ.rights_verdict} />}
            {econ.scenarios?.policy && econ.scenarios.cap_400 && (
              <ComparisonTable policy={econ.scenarios.policy} cap={econ.scenarios.cap_400} />
            )}

            {/* ‏C14 · הסייג צמוד למספר שהוא מסייג. הנוסח מהשרת, כמו
                ‏`not_delivered_reason` — אותו משפט במסך, ב-PDF ובאקסל. */}
            {d.economics.caveats.length > 0 && (
              <Alert color="almond" title="על מה הרווח נשען" mt="md">
                <List size="sm" spacing={4}>
                  {d.economics.caveats.map((c) => <List.Item key={c.id}>{c.text}</List.Item>)}
                </List>
              </Alert>
            )}

            {unitReview && unitReview.total > 0 && (
              <Text size="sm" c="dimmed" mt="md">
                {unitReview.pending > 0
                  ? `${unitReview.pending} מתוך ${unitReview.total} הדירות שנקראו מההיתר ממתינות לאישור. `
                  : `כל ${unitReview.total} הדירות שנקראו מההיתר אושרו. `}
                <Link href={`/app/dossier/${id}/units`} className="text-link">
                  {unitReview.pending > 0 ? "אשר דירות ←" : "לוח הדירות ←"}
                </Link>
              </Text>
            )}

            {/* ‏B15 · התמהיל שהיזם חישב. המשפט מהשרת, כמו ב-PDF ובאקסל,
                והרווח שמעליו אינו זז בגללו (בועז, 15.09). */}
            <Paper withBorder={false} bg="var(--ground-2)" p="sm" mt="md" mb="md">
              <Text size="sm">
                {d.economics.unit_mix?.summary ? (
                  <>
                    {d.economics.unit_mix.summary}{" "}
                    <Link href={`/app/dossier/${id}/mix`} className="text-link">שנה את התמורה ←</Link>
                  </>
                ) : (
                  <>
                    תמהיל הדירות עוד לא חושב.{" "}
                    <Link href={`/app/dossier/${id}/mix`} className="text-link">חשב תמהיל ורווחיות ←</Link>
                  </>
                )}
              </Text>
            </Paper>

            <Table>
              <Table.Tbody>
                {econ.cost_rows ? econ.cost_rows.map((row) => (
                  <Table.Tr key={row.id}>
                    <Table.Td><WithRowInfo row={row} /></Table.Td>
                    <Table.Td ta="end" className={`num ${row.value_ils < 0 ? "text-bad" : "text-ok"}`} fw={600}>
                      {ilsApprox(row.value_ils)}
                    </Table.Td>
                  </Table.Tr>
                )) : ([
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
                  ...(d.economics.betterment ? [] : [["היטל השבחה", -s.betterment_levy_ils]]),
                ] as [string, number][]).map(([name, value]) => (
                  <Table.Tr key={name}>
                    <Table.Td>{name}</Table.Td>
                    <Table.Td ta="end" className={`num ${value < 0 ? "text-bad" : "text-ok"}`} fw={600}>
                      {ilsApprox(value)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                <Table.Tr>
                  <Table.Td fw={700}>{after ? "רווח אחרי אומדן היטל" : "רווח"}</Table.Td>
                  <Table.Td ta="end" className={`num ${s.projected_profit_ils < 0 ? "text-bad" : "text-ok"}`} fw={700}>
                    {ilsApprox(s.projected_profit_ils)}
                  </Table.Td>
                </Table.Tr>
                {/* ‏B13 · שורת ההיטל נכתבת פעם אחת בשרת, וה-PDF והאקסל מדפיסים
                    אותה כמו שהיא. נוסח מקומי כאן היה נפרד מהם בשקט. */}
                {d.economics.betterment && (
                  <Table.Tr>
                    <Table.Td colSpan={2} className="text-warn" fw={600}>
                      {d.economics.betterment.summary}
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>

            {d.economics.betterment && <BettermentBlock b={d.economics.betterment} />}
          </>
        ) : (
          <Text className="text-warn">{d.economics.why ?? "לא חושב תרחיש."}</Text>
        )}

        {/* המשפט נכתב בשרת ולא כאן. הוא הופיע קודם בשלושה נוסחים —
            במסך, ב-PDF וב-Excel — וכל שלושתם צירפו מזהי קוד. */}
        {!d.economics.is_deliverable && d.economics.not_delivered_reason && (
          <Alert color="almond" mt="md">{d.economics.not_delivered_reason}</Alert>
        )}

        <Accordion variant="contained" mt="md" radius="sm">
          <Accordion.Item value="assumptions">
            <Accordion.Control><Text size="sm" fw={600}>כל ההנחות · גרסה {d.economics.assumptions_version}</Text></Accordion.Control>
            <Accordion.Panel>
              <Table.ScrollContainer minWidth={520}>
                <Table>
                  <Table.Tbody>
                    {Object.entries(d.economics.assumptions).map(([k, a]) => (
                      <Table.Tr key={k}>
                        <Table.Td>{a.label}</Table.Td>
                        <Table.Td className="num">{assumptionValue(a)}</Table.Td>
                        <Table.Td>{assumptionBadge(a.status)}</Table.Td>
                        <Table.Td c="dimmed" fz="sm">{a.source ?? "—"}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Section>

      <Section id="gaps" title="פערים" note={d.gaps.note}>
        {[
          ["שערים שלא נענו", d.gaps.unknown_gates.map((g) => g.label)],
          ["אין להם מקור פתוח", d.gaps.unobtainable.map((x) => x.label)],
          ["נבדק ולא נמצא", d.gaps.checked_and_not_found.map((x) => x.label)],
          ["מעולם לא נשאל", d.gaps.never_asked.map((x) => x.label)],
          ["מקורות שהתיישנו", d.gaps.stale_sources.map((x) => x.label)],
        ].map(([title, items]) => (
          <Text key={title as string} size="sm" mb={6}>
            <strong>{title}: </strong>
            <span className={(items as string[]).length ? undefined : "text-muted"}>
              {(items as string[]).length ? (items as string[]).join(" · ") : "אין"}
            </span>
          </Text>
        ))}
      </Section>

      <Text size="xs" c="dimmed" pb="xl">
        כללים {d.versions.rules_version} · נתונים {d.versions.data_version || "—"} ·
        תבנית {d.versions.template_version}
      </Text>
    </GlossaryContext.Provider>
  );
}
