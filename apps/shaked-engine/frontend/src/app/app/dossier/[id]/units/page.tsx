"use client";

import { Alert, Anchor, Button, Group, NumberInput, Paper, SimpleGrid, Table, Text, TextInput } from "@mantine/core";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { PageHeader, Section, Stat, StatStrip, StatusBadge, gateBadge } from "@/components/brand/ui";
import { ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import {
  RESIDENTIAL_SHARE_MIN, getResidentialShare, saveResidentialShare, shareOf, sharePct,
  type ResidentialShareState,
} from "@/lib/residential";

type UnitRow = {
  id: string;
  source_key: string;
  unit_label: string | null;
  floor: string | null;
  area_sqm: number | null;
  certainty: string;
  requires_human_review: boolean;
  source_url: string | null;
  retrieved_at: string | null;
  location: string | null;
  method: string | null;
  raw_text: string | null;
};

type ReviewState = {
  opportunity_id: string;
  address: string;
  municipal_unit_count: number | null;
  units: UnitRow[];
  resolution: {
    average_existing_unit_sqm: number | null;
    source: string;
    certainty: string;
    per_unit_detail_available: boolean;
    unit_count: number | null;
    schedule_complete: boolean;
    has_unit_count_conflict: boolean;
    may_decide: boolean;
    notes: string[];
  };
};

type Draft = { unit_label: string; floor: string; area_sqm: string };

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = window.localStorage.getItem("shaked_token");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401) throw new Error("AUTH");
  if (!response.ok) {
    let detail = "הפעולה נכשלה.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch { /* no-op */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function draftFor(unit: UnitRow): Draft {
  return {
    unit_label: unit.unit_label ?? "",
    floor: unit.floor ?? "",
    area_sqm: unit.area_sqm == null ? "" : String(unit.area_sqm),
  };
}

const num = (v: string | number) => (v === "" ? null : Number(v));

/** ‏W10 · §70א — יחס המגורים מטבלת השטחים בגרמושקה, שמכריע את שער ה-70%. */
function ResidentialShareSection({ id }: { id: string }) {
  const router = useRouter();
  const [share, setShare] = useState<ResidentialShareState | null>(null);
  const [residential, setResidential] = useState<string | number>("");
  const [total, setTotal] = useState<string | number>("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [page, setPage] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getResidentialShare(id)
      .then((s) => { setShare(s); setSourceUrl(s.entry?.source_url ?? ""); })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) { router.replace("/login"); return; }
        setError(e instanceof Error ? e.message : "לא ניתן לטעון את יחס המגורים.");
      });
  }, [id, router]);

  const r = num(residential);
  const t = num(total);
  const tooLarge = r != null && t != null && r > t;
  const live = r != null && t != null && r > 0 && t > 0 && !tooLarge ? shareOf(r, t) : null;
  const urlOk = /^https?:\/\/\S+$/.test(sourceUrl.trim());
  const canSave = live != null && urlOk && !saving;

  async function save() {
    if (live == null || r == null || t == null) return;
    setSaving(true);
    setError(null);
    try {
      const next = await saveResidentialShare(id, {
        residential_sqm: r, total_sqm: t, source_url: sourceUrl.trim(),
        page: page.trim() || null, note: note.trim() || null,
      });
      setShare(next);
      setResidential(""); setTotal(""); setPage(""); setNote("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { router.replace("/login"); return; }
      setError(e instanceof Error ? e.message : "לא ניתן לשמור את יחס המגורים.");
    } finally {
      setSaving(false);
    }
  }

  const entry = share?.entry;
  return (
    <Section
      title="70% מגורים — מטבלת השטחים בהיתר"
      note={<>
        ‏§70א הוא תנאי סף לחלופת שקד: לפחות 70% מהשטח הבנוי הקיים צריך לשמש כדין למגורים.
        היחס אינו בשום מקור פתוח — קוראים אותו בטבלת השטחים שבגרמושקה ומזינים כאן, והוא מכריע את השער בתיק.
        {" "}<b>שטחי שירות למגורים נספרים כמגורים</b> (חדרי מדרגות, מעליות, ממ״דים); מסחר, משרדים והשירות שלהם — לא.
      </>}
    >
      {share && (
        <>
          <StatStrip>
            <Stat label="יחס שמור" value={entry ? sharePct(entry.residential_share) : "—"} />
            <Stat label="שער ה-70%" value={gateBadge(share.gate.status)} />
            <Stat label="הוזן" value={entry ? fmtDate(entry.retrieved_at) : "טרם הוזן"} />
            <Stat label="ניתן למסירה" value={share.assessment.deliverable ? "כן" : "לא"}
                  tone={share.assessment.deliverable ? "ok" : "warn"} />
          </StatStrip>
          {share.gate.detail && <Text size="sm" c="dimmed" mt="sm">{share.gate.detail}</Text>}
          {entry?.source_url && (
            <Anchor href={entry.source_url} target="_blank" rel="noreferrer" size="sm" c="almond.7">פתח את הגרמושקה שהוזנה</Anchor>
          )}
          {share.stale && (
            <Alert color="almond" mt="sm">ההזנה ישנה מכדי להכריע. יש לבדוק שוב מול הגרמושקה ולשמור מחדש.</Alert>
          )}
          {share.certainty === "conflict" && (
            <Alert color="brick" mt="sm">ההזנה סותרת קריאה אחרת של אותו יחס, ולכן השער אינו מוכרע.</Alert>
          )}
        </>
      )}

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" mt="lg">
        <NumberInput label="שטח מגורים, כולל שירות למגורים" description="מ״ר, מטבלת השטחים" min={0} max={100000}
                     hideControls decimalScale={2} value={residential} onChange={setResidential}
                     error={tooLarge ? "שטח המגורים אינו יכול לעלות על השטח הבנוי הכולל" : undefined} />
        <NumberInput label="שטח בנוי כולל" description="מ״ר, כל השימושים וכל שטחי השירות" min={0} max={100000}
                     hideControls decimalScale={2} value={total} onChange={setTotal} />
        <TextInput label="קישור לגרמושקה" description="המסמך שממנו נקראה הטבלה" placeholder="https://…" dir="ltr"
                   value={sourceUrl} onChange={(e) => setSourceUrl(e.currentTarget.value)}
                   error={sourceUrl.trim() && !urlOk ? "קישור מלא, שמתחיל ב-https://" : undefined} />
        <TextInput label="עמוד בגרמושקה" description="לא חובה" maxLength={20}
                   value={page} onChange={(e) => setPage(e.currentTarget.value)} />
      </SimpleGrid>
      <TextInput label="הערה" description="לא חובה · מוצגת בתיק ליד המקור" maxLength={300} mt="md"
                 value={note} onChange={(e) => setNote(e.currentTarget.value)} />

      <Group justify="space-between" mt="md" wrap="wrap">
        <Text size="sm" fw={600} c={live == null ? "dimmed" : live >= RESIDENTIAL_SHARE_MIN ? "moss.7" : "brick.7"}>
          {live == null ? "היחס יחושב כשיוזנו שני השטחים"
            : live >= RESIDENTIAL_SHARE_MIN ? `${sharePct(live)} מגורים — עומד בסף ה-70%`
            : `${sharePct(live)} מגורים — מתחת ל-70%, השער ייכשל`}
        </Text>
        <Button loading={saving} disabled={!canSave} onClick={save}>
          {entry ? "שמור במקום ההזנה הקודמת" : "שמור והכרע את השער"}
        </Button>
      </Group>
      {error && <Alert color="brick" mt="md">{error}</Alert>}
    </Section>
  );
}

export default function DwellingUnitReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [state, setState] = useState<ReviewState | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  const sync = (next: ReviewState) => {
    setState(next);
    setDrafts(Object.fromEntries(next.units.map((u) => [u.id, draftFor(u)])));
  };

  useEffect(() => {
    api<ReviewState>(`/api/v1/dossiers/${id}/dwelling-units`)
      .then(sync)
      .catch((e) => {
        if (e instanceof Error && e.message === "AUTH") { router.replace("/login"); return; }
        setError(e instanceof Error ? e.message : "לא ניתן לטעון את הדירות.");
      });
  }, [id, router]);

  async function review(unit: UnitRow, action: "confirm" | "reject") {
    const draft = drafts[unit.id] ?? draftFor(unit);
    setSaving(unit.id);
    setError(null);
    try {
      const body = action === "confirm" ? {
        action,
        unit_label: draft.unit_label || null,
        floor: draft.floor || null,
        area_sqm: draft.area_sqm === "" ? null : Number(draft.area_sqm),
      } : { action };
      const next = await api<ReviewState>(
        `/api/v1/dossiers/${id}/dwelling-units/${unit.id}`,
        { method: "PATCH", body: JSON.stringify(body) },
      );
      sync(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "לא ניתן לשמור את הבדיקה.");
    } finally {
      setSaving(null);
    }
  }

  if (!state) {
    return error ? <Alert color="brick" title={error} /> : <Text c="dimmed">טוען…</Text>;
  }

  const r = state.resolution;
  const setDraft = (unitId: string, d: Draft, patch: Partial<Draft>) =>
    setDrafts((x) => ({ ...x, [unitId]: { ...d, ...patch } }));

  return (
    <>
      <PageHeader
        back={{ href: `/app/dossier/${id}`, label: "חזרה לתיק" }}
        eyebrow="תיק הזדמנות · הרצליה"
        title="אימות שטחי הדירות"
        meta={<>{state.address} · ספירה עירונית: {state.municipal_unit_count ?? "—"} דירות</>}
      />

      <ResidentialShareSection id={id} />

      <Section title="מצב הלוח">
        <StatStrip>
          <Stat label="שורות עם שטח" value={r.unit_count ?? 0} />
          <Stat label="ממוצע מאומת" value={r.average_existing_unit_sqm == null ? "—" : `${r.average_existing_unit_sqm} מ״ר`} />
          <Stat label="לוח שלם" value={r.schedule_complete ? "כן" : "לא"} tone={r.schedule_complete ? "ok" : undefined} />
          <Stat label="רשאי להכריע תרחיש" value={r.may_decide ? "כן" : "לא"} tone={r.may_decide ? "ok" : "warn"} />
        </StatStrip>
        {r.has_unit_count_conflict && (
          <Alert color="brick" mt="md">יש סתירה בין מספר הדירות בלוח לבין הספירה העירונית.</Alert>
        )}
        {r.notes.map((note) => <Text key={note} size="sm" c="dimmed" mt="sm">{note}</Text>)}
      </Section>

      {error && <Alert color="brick" mb="md">{error}</Alert>}

      {state.units.length === 0 ? (
        <Paper p="lg">
          <Text fw={700}>עדיין אין שורות דירה לחוות עליהן דעה.</Text>
          <Text size="sm" c="dimmed" mt={4}>יש להריץ קודם את יצירת התיק כדי שמנוע B3 יחלץ את לוח הדירות מהגרמושקה.</Text>
        </Paper>
      ) : (
        <Paper p="lg">
          <Table.ScrollContainer minWidth={820}>
            <Table verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>דירה</Table.Th><Table.Th>קומה</Table.Th><Table.Th>שטח</Table.Th>
                  <Table.Th>מצב</Table.Th><Table.Th>מקור</Table.Th><Table.Th>פעולה</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {state.units.map((unit) => {
                  const d = drafts[unit.id] ?? draftFor(unit);
                  const verified = !unit.requires_human_review && unit.certainty === "manually_verified";
                  const rejected = unit.method === "manual_rejected";
                  return (
                    <Table.Tr key={unit.id}>
                      <Table.Td><TextInput size="xs" w={90} value={d.unit_label} onChange={(e) => setDraft(unit.id, d, { unit_label: e.currentTarget.value })} /></Table.Td>
                      <Table.Td><TextInput size="xs" w={80} value={d.floor} onChange={(e) => setDraft(unit.id, d, { floor: e.currentTarget.value })} /></Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          <NumberInput size="xs" w={110} min={15} max={400} step={0.01} hideControls
                                       value={d.area_sqm === "" ? "" : Number(d.area_sqm)}
                                       onChange={(v) => setDraft(unit.id, d, { area_sqm: v === "" ? "" : String(v) })} />
                          <Text size="sm" c="dimmed">מ״ר</Text>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <StatusBadge tone={verified ? "ok" : rejected ? "bad" : "warn"}>
                          {verified ? "אומת ידנית" : rejected ? "נדחה — חילוץ מחדש" : "דורש בדיקה"}
                        </StatusBadge>
                      </Table.Td>
                      <Table.Td>
                        {unit.source_url ? <Anchor href={unit.source_url} target="_blank" rel="noreferrer" size="sm" c="almond.7">פתח מסמך</Anchor> : <Text size="sm" c="dimmed">אין מקור</Text>}
                        {unit.location && <Text size="xs" c="dimmed" maw={260}>{unit.location}</Text>}
                        {unit.raw_text && <Text size="xs" c="dimmed" maw={260}>OCR: {unit.raw_text}</Text>}
                      </Table.Td>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>
                        <Group gap={6} wrap="nowrap">
                          <Button size="xs" loading={saving === unit.id} disabled={saving !== null && saving !== unit.id}
                                  onClick={() => review(unit, "confirm")}>
                            {verified ? "שמור תיקון" : "אשר"}
                          </Button>
                          <Button size="xs" variant="default" c="brick.7" disabled={saving !== null}
                                  onClick={() => review(unit, "reject")}>
                            דחה
                          </Button>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
    </>
  );
}
