"use client";

import { Accordion, Alert, Anchor, Button, Group, List, Paper, Table, Text } from "@mantine/core";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { use } from "react";
import { ApiError, downloadDossier, getDossier, getUnitReviewCounts,
         type Betterment, type Dossier, type EvidenceRow, type Gate } from "@/lib/api";
import { fmtDate as date, ils, ilsApprox, sqm } from "@/lib/format";
import type { Tone } from "@/lib/labels";
import { IconFile, IconSheet } from "@/components/brand/icons";
import { assumptionBadge, gateBadge, PageHeader, Section, Stat, StatStrip, StatusBadge } from "@/components/brand/ui";

const CITY = "herzliya";

/** שער אחד בשרשרת, עם הסעיף שאפשר לפתוח ולבדוק אותנו לפיו. */
function GateRow({ gate }: { gate: Gate }) {
  return (
    <Table.Tr>
      <Table.Td w="7rem">{gateBadge(gate.status)}</Table.Td>
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
            <Table.Th>שדה</Table.Th><Table.Th>ערך</Table.Th><Table.Th>ודאות</Table.Th>
            <Table.Th>מכריע?</Table.Th><Table.Th>נשלף</Table.Th><Table.Th>מקור</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => (
            <Table.Tr key={r.field}>
              {/* התווית מגיעה מהשרת — מקור אמת אחד ל-PDF, ל-Excel ולמסך.
                  המפה המקומית הוסרה: ״גיבוי״ שאיש אינו רואה כשהוא נכנס
                  לפעולה אינו גיבוי אלא באג שקט. אם השרת לא שלח תווית,
                  בדיקת `test_labels.py` כבר נפלה. */}
              <Table.Td fw={600}>{r.label}</Table.Td>
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
          label={`תקרת היטל ההשבחה · ${Math.round(levy.rate * 100)}% מההשבחה`}
          value={levy.viable_up_to_ils != null ? `עד ${ilsApprox(levy.viable_up_to_ils)}` : "אין תקרה"}
          tone={tone}
        />
        {b.breakeven_land_value_per_right_ils != null && (
          <Stat label="שווי מ״ר זכויות שבו הרווח יורד למזערי" value={ils(b.breakeven_land_value_per_right_ils)} />
        )}
        {levy.low_ils != null && levy.high_ils != null && (
          <Stat label="אומדן ההיטל" value={`${ilsApprox(levy.low_ils)}–${ilsApprox(levy.high_ils)}`} />
        )}
      </StatStrip>
      <Group gap="xs" mt="sm">
        <StatusBadge tone={tone}>{b.category_label}</StatusBadge>
        {levy.within_range === false && (
          <Text size="sm" fw={600} className="text-bad">הקצה העליון של אומדן ההיטל גבוה מהתקרה.</Text>
        )}
      </Group>
      <Text size="sm" c="dimmed" mt={6}>{b.note}</Text>
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

  // ‏C15 · מסך האישור (PR #17) קיים, ועד היום לא היה מקושר מהתיק עם מה שמחכה בו.
  const [unitReview, setUnitReview] = useState<{ total: number; pending: number } | null>(null);
  useEffect(() => {
    getUnitReviewCounts(id).then(setUnitReview).catch(() => setUnitReview(null));
  }, [id]);

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
      <>
        <Alert color="brick" title={error} />
        <p style={{ marginTop: "1rem" }}><Link href="/dashboard" className="text-link">← חזרה למסך החיפוש</Link></p>
      </>
    );
  }
  if (!d) return <Text c="dimmed">טוען…</Text>;

  const f = d.rights.floors;
  const floorsText = f.low === null ? "—"
    : f.high !== null && f.high !== f.low ? `${f.low}–${f.high}` : String(f.low);
  const s = d.economics.scenario as Record<string, number> | null;

  return (
    <>
      <PageHeader
        back={{ href: "/dashboard", label: "חזרה" }}
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
        title="שרשרת הזכויות"
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
              label="קומות מותרות"
              value={floorsText}
              hint={f.case_by_case ? "בחינה נקודתית" : f.certain ? undefined : "דורש מדידה"}
            />
            <Stat
              label="תקרת 400%"
              value={d.rights.cap_400_sqm ? sqm(d.rights.cap_400_sqm) : "—"}
              hint={d.rights.cap_400_certainty === "estimate" ? "על אומדן" : undefined}
            />
            {d.rights.unit_mix && (
              <Stat label="יחידות אחרי" value={`${d.rights.unit_mix.units_min}–${d.rights.unit_mix.units_max}`} />
            )}
            {d.rights.parking?.spaces != null && (
              <Stat label="חניות" value={String(d.rights.parking.spaces)} />
            )}
          </StatStrip>
        </div>

        {d.rights.cap_400_basis && <Text size="sm" c="dimmed" mt="md">{d.rights.cap_400_basis}</Text>}
        {d.rights.notes.map((n) => <Text key={n} size="sm" c="dimmed" mt={4}>{n}</Text>)}
      </Section>

      <Section
        id="evidence"
        title="מאיפה הגיע כל מספר"
        note="מקור, מועד וודאות לכל שדה מהותי. ״מכריע״ פירושו שהתצפית רשאית להכריע שער — ודאות, מקור, מיקום וגיל, כולם יחד."
      >
        <EvidenceTable rows={d.evidence} />
      </Section>

      <Section id="economics" title="תרחיש כלכלי" note={d.economics.disclaimer}>
        {s ? (
          <>
            <StatStrip cols={{ base: 1, sm: 3 }}>
              <Stat
                label={`רווח צפוי${d.economics.betterment ? " · לפני היטל השבחה" : ""}`}
                value={ilsApprox(s.projected_profit_ils)}
              />
              <Stat
                label="רווח על העלות"
                value={`${Math.round(s.profit_margin_on_cost_ratio * 100)}%`}
                tone={s.meets_developer_target ? "ok" : "warn"}
              />
              {/* ‏C14 · היה ״שטח נמכר״, והמספר הוא השטח שנשאר ליזם אחרי הדיירים.
                  באקסל ״שטח נמכר (עיקרי)״ הוא כל השטח העיקרי — שם אחד, שני
                  מספרים, בדיוק ברגע שהיזם פותח את האקסל מול המסך. */}
              <Stat label="שטח ליזם" value={sqm(s.developer_allocation_sqm)} />
            </StatStrip>

            {/* ‏E1 · מעל או מתחת ל-16%, במילים ולא רק בצבע. המשפט מהשרת, כמו ב-PDF ובאקסל. */}
            {d.economics.profit_verdict && (
              <Text size="sm" fw={600} mt="sm" className={s.meets_developer_target ? "text-ok" : "text-warn"}>
                {d.economics.profit_verdict}
              </Text>
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
                <Link href={`/dossier/${id}/units`} className="text-link">
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
                    <Link href={`/dossier/${id}/mix`} className="text-link">שנה את התמורה ←</Link>
                  </>
                ) : (
                  <>
                    תמהיל הדירות עוד לא חושב.{" "}
                    <Link href={`/dossier/${id}/mix`} className="text-link">חשב תמהיל ורווחיות ←</Link>
                  </>
                )}
              </Text>
            </Paper>

            <Table>
              <Table.Tbody>
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
                  <Table.Tr key={name}>
                    <Table.Td>{name}</Table.Td>
                    <Table.Td ta="end" className={`num ${value < 0 ? "text-bad" : "text-ok"}`} fw={600}>
                      {ilsApprox(value)}
                    </Table.Td>
                  </Table.Tr>
                ))}
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
                        <Table.Td className="num">
                          {a.value.toLocaleString("he-IL")} <Text span c="dimmed" size="sm">{a.unit}</Text>
                        </Table.Td>
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
    </>
  );
}
