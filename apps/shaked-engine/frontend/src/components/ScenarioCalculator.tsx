"use client";

import { Alert, Badge, Button, Group, List, NumberInput, Paper, Select, SimpleGrid, Table, Text } from "@mantine/core";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { ilsApprox, sqm } from "@/lib/format";
import { downloadScenario, runScenario } from "@/lib/scenario";
import type {
  AreaBasis, MixRow, OverrideApplied, PolicyDossier, ScenarioEconomics, ScenarioOverrides, ScenarioResponse,
} from "@/lib/dossier";
import { IconFile, IconSheet } from "@/components/brand/icons";
import { Stat, StatStrip } from "@/components/brand/ui";
import { WithRowInfo } from "@/components/CostRowInfo";
import { WithTerm } from "@/components/Term";

/** ‏W8 · מחשבון התרחיש, בתוך הדוח הכלכלי (בקשות 12 ו-14 של השותפים).
 *
 *  הנתונים שלנו הם ברירת המחדל. היזם משנה ערכים או בוחר תמהיל, והשרת מחשב את
 *  אותו דוח 0 מחדש — הרווח אחרי היטל, המשפט ליד הרווח, שורות העלות והתמהיל.
 *  **החישוב כולו בשרת**: עותק של החשבון בדפדפן היה נפרד בשקט מה-PDF ומהאקסל.
 *  שום דבר אינו נשמר. */

type Num = number | string;
type Rooms = 3 | 4 | 5;
const ROOMS: Rooms[] = [3, 4, 5];
// אותם גדלים כמו בשרת (`unit_mix/service.py`, ‏DEFAULT_UNIT_AREAS_SQM) — הנחת מודל, לא הוראה עירונית.
const ROOM_SQM: Record<Rooms, number> = { 3: 75, 4: 100, 5: 125 };
const DEBOUNCE_MS = 500;

interface Form {
  areaBasis: AreaBasis;
  customArea: Num;
  salePrice: Num;
  constructionCost: Num;
  compensation: Num;
  existingPrice: Num;
  targetPct: Num;
  financePct: Num;
  unitArea: Num;
  undergroundCost: Num;
  betterment: Num;
  mixMode: "none" | "optimize" | "manual";
  mix: Record<Rooms, Num>;
}

type NumericField = Exclude<keyof Form, "areaBasis" | "mixMode" | "mix">;

/** טווחים — אותם כמו בשרת (`scenario.py`). ערך מחוץ לטווח אינו נשלח. */
const RANGE: Record<NumericField, [number, number]> = {
  customArea: [1, 500_000],
  salePrice: [5_000, 200_000],
  constructionCost: [1_000, 50_000],
  compensation: [0, 100],
  existingPrice: [1_000, 200_000],
  targetPct: [0, 100],
  financePct: [0, 50],
  unitArea: [20, 500],
  undergroundCost: [0, 50_000],
  betterment: [0, 10_000_000_000],
};

const num = (v: Num | null | undefined): number | null => {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v !== "string" || v.trim() === "") return null;
  const x = Number(v.replace(/,/g, ""));
  return Number.isFinite(x) ? x : null;
};
const round4 = (x: number) => Math.round(x * 10_000) / 10_000;
const pct = (x: number | null | undefined, digits = 1) =>
  x == null ? "—" : `${(x * 100).toLocaleString("he-IL", { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;

function defaultsOf(econ: PolicyDossier["economics"], rights: PolicyDossier["rights"]): Form {
  const a = econ.assumptions;
  const v = (key: string): Num => a[key]?.value ?? "";
  const live = (econ as ScenarioEconomics).live_inputs;
  return {
    areaBasis: rights.policy_area?.base ? "policy_base" : "cap_400",
    customArea: "",
    salePrice: v("sale_price_per_sqm_ils"),
    constructionCost: v("construction_cost_per_sqm_ils"),
    compensation: v("tenant_compensation_sqm_per_existing_unit"),
    existingPrice: live?.existing_price?.value ?? "",
    targetPct: a.developer_profit_target_ratio ? round4(a.developer_profit_target_ratio.value * 100) : "",
    financePct: a.finance_ratio ? round4(a.finance_ratio.value * 100) : "",
    unitArea: v("average_existing_unit_sqm"),
    undergroundCost: v("underground_cost_per_sqm_ils"),
    // ההשבחה אינה שדה עם ערך: ריק = האומדן שלנו (או סף בלבד, כשאין אומדן).
    betterment: "",
    mixMode: "none",
    mix: { 3: "", 4: "", 5: "" },
  };
}

function changed(form: Form, d: Form, field: NumericField): boolean {
  const x = num(form[field]);
  if (x === null) return false;
  const y = num(d[field]);
  return y === null || Math.abs(x - y) > 1e-9;
}

function invalid(form: Form, field: NumericField, maxArea?: number | null): boolean {
  const x = num(form[field]);
  if (x === null) return false;
  const [lo, hi] = RANGE[field];
  return x < lo || x > (field === "customArea" && maxArea ? maxArea : hi);
}

/** רק מה שהיזם שינה. ערך שזהה לברירת המחדל אינו נשלח — הוא אינו ״הוזן על ידי היזם״. */
function bodyOf(form: Form, d: Form): ScenarioOverrides {
  const out: ScenarioOverrides = {};
  if (form.areaBasis !== d.areaBasis) {
    out.area_basis = form.areaBasis;
    if (form.areaBasis === "custom") out.custom_area_sqm = num(form.customArea) ?? undefined;
  }
  const put = (field: NumericField, key: keyof ScenarioOverrides, scale = 1) => {
    if (changed(form, d, field)) (out as Record<string, unknown>)[key] = Math.round(num(form[field])! / scale * 1e6) / 1e6;
  };
  put("salePrice", "sale_price_per_sqm");
  put("constructionCost", "construction_cost_per_sqm");
  put("undergroundCost", "underground_cost_per_sqm");
  put("compensation", "tenant_compensation_sqm_per_existing_unit");
  put("unitArea", "average_existing_unit_sqm");
  put("existingPrice", "existing_price_per_sqm");
  put("targetPct", "developer_profit_target_ratio", 100);
  put("financePct", "finance_ratio", 100);
  if (num(form.betterment) !== null) out.betterment_ils = num(form.betterment)!;
  if (form.mixMode === "optimize") out.mix = "optimize";
  if (form.mixMode === "manual") {
    const rows: MixRow[] = ROOMS.map((rooms) => ({ rooms, units: Math.round(num(form.mix[rooms]) ?? 0) }))
      .filter((r) => r.units > 0);
    if (rows.length) out.mix = rows;
  }
  return out;
}

function overrideValue(value: number | string | null, unit: string): string {
  if (value === null || value === undefined) return "אין";
  if (typeof value === "string") return value;
  if (unit === "ratio") return pct(value, 2).replace(/\.?0+%$/, "%");
  if (unit === "sqm") return sqm(value);
  if (unit === "ILS") return ilsApprox(value);
  if (unit === "ILS/sqm") return `${Math.round(value).toLocaleString("he-IL")} ₪ למ״ר`;
  return value.toLocaleString("he-IL");
}

function ChangedList({ items }: { items: OverrideApplied[] }) {
  if (!items.length) return <Text size="sm" c="dimmed">לא שינית אף ערך — אלה המספרים של התיק.</Text>;
  return (
    <List size="sm" spacing={2}>
      {items.map((o) => (
        <List.Item key={o.id}>
          <strong>{o.label}:</strong> {overrideValue(o.value, o.unit)}
          {o.id !== "mix" && <Text span size="sm" c="dimmed"> · ברירת המחדל {overrideValue(o.default, o.unit)}</Text>}
        </List.Item>
      ))}
    </List>
  );
}

export function ScenarioCalculator({ cityCode, opportunityId, econ, rights }: {
  cityCode: string;
  opportunityId: string;
  econ: PolicyDossier["economics"];
  rights: PolicyDossier["rights"];
}) {
  const defaults = useMemo(() => defaultsOf(econ, rights), [econ, rights]);
  const [form, setForm] = useState<Form>(defaults);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  // הבקשה שממנה חושבה התוצאה המוצגת — כדי לדעת מתי היא כבר אינה עדכנית.
  const [resultKey, setResultKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "xlsx" | null>(null);
  const inFlight = useRef<AbortController | null>(null);

  const cap = rights.cap_400_sqm;
  const policy = rights.policy_area;
  const fields = Object.keys(RANGE) as NumericField[];
  const hasInvalid = fields.some((f) => invalid(form, f, cap))
    || (form.areaBasis === "custom" && num(form.customArea) === null);
  const body = useMemo(() => bodyOf(form, defaults), [form, defaults]);
  const key = JSON.stringify(body);
  const untouched = key === "{}";

  function set<K extends keyof Form>(field: K, value: Form[K]) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function compute(request: ScenarioOverrides) {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setBusy(true);
    try {
      const r = await runScenario(cityCode, opportunityId, request, controller.signal);
      if (controller.signal.aborted) return;
      setResult(r);
      setResultKey(JSON.stringify(request));
      setError(null);
      // התמהיל המיטבי ממלא את העורך, כדי שאפשר יהיה לשנות ממנו דירה או שתיים.
      const rows = r.economics.unit_mix?.rows ?? [];
      if (request.mix === "optimize" && rows.length) {
        setForm((f) => (f.mixMode !== "optimize" ? f : {
          ...f, mix: { 3: 0, 4: 0, 5: 0, ...Object.fromEntries(rows.map((x) => [x.rooms, x.units])) } as Record<Rooms, Num>,
        }));
      }
    } catch (e) {
      if (controller.signal.aborted || (e instanceof DOMException && e.name === "AbortError")) return;
      setResult(null);
      setError(e instanceof ApiError ? e.detail : "לא ניתן לחשב את התרחיש כרגע.");
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setBusy(false);
      }
    }
  }

  // חישוב מחדש חצי שנייה אחרי השינוי האחרון. בלי שינוי — המספרים של התיק, בלי בקשה.
  useEffect(() => {
    if (hasInvalid) return;
    if (untouched) {
      inFlight.current?.abort();
      setResult(null);
      setResultKey(null);
      setError(null);
      setBusy(false);
      return;
    }
    const t = setTimeout(() => compute(body), DEBOUNCE_MS);
    return () => clearTimeout(t);
    // ‏`key` מייצג את `body`; ‏compute קורא רק ממה שמועבר אליו.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, hasInvalid]);

  useEffect(() => () => inFlight.current?.abort(), []);

  function reset() {
    inFlight.current?.abort();
    setForm(defaults);
    setResult(null);
    setResultKey(null);
    setError(null);
    setBusy(false);
  }

  async function download(fmt: "pdf" | "xlsx") {
    setDownloading(fmt);
    try {
      await downloadScenario(cityCode, opportunityId, fmt, body);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "ההורדה נכשלה.");
    } finally {
      setDownloading(null);
    }
  }

  // ── התוצאה: התרחיש שחושב, ועד שהוא מגיע — המספרים הקודמים, מעומעמים ──
  const shown: ScenarioEconomics = result?.economics ?? (econ as ScenarioEconomics);
  const s = shown.scenario as Record<string, number> | null;
  const after = shown.after_levy ?? null;
  const stale = busy || (untouched ? result !== null && resultKey !== "{}" : resultKey !== key);

  const areaOptions = [
    policy?.low && { value: "policy_low", label: `לפי המדיניות — נמוך · ${sqm(policy.low.sqm)}` },
    policy?.base && { value: "policy_base", label: `לפי המדיניות — בסיס · ${sqm(policy.base.sqm)}` },
    policy?.high && { value: "policy_high", label: `לפי המדיניות — גבוה · ${sqm(policy.high.sqm)}` },
    cap && { value: "cap_400", label: `תקרת 400% (תאורטית) · ${sqm(cap)}` },
    { value: "custom", label: "שטח אחר — הזנה" },
  ].filter(Boolean) as { value: AreaBasis; label: string }[];

  function numberField(field: NumericField, label: ReactNode, props: {
    suffix?: string; step?: number; hint?: string; placeholder?: string; thousands?: boolean; decimals?: boolean;
  } = {}) {
    const isChanged = changed(form, defaults, field) || (field === "betterment" && num(form.betterment) !== null);
    const d = num(defaults[field]);
    return (
      <NumberInput
        label={<Group gap={6} wrap="nowrap" component="span">{label}{isChanged && <Badge size="xs" color="almond">שונה</Badge>}</Group>}
        description={props.hint ?? (d !== null ? `ברירת המחדל: ${d.toLocaleString("he-IL")}${props.suffix ?? ""}` : undefined)}
        placeholder={props.placeholder}
        value={form[field]}
        onChange={(v) => set(field, v)}
        min={RANGE[field][0]}
        max={field === "customArea" && cap ? cap : RANGE[field][1]}
        step={props.step ?? 1}
        allowDecimal={props.decimals ?? false}
        allowNegative={false}
        thousandSeparator={props.thousands ? "," : undefined}
        clampBehavior="none"
        error={invalid(form, field, cap) ? "מחוץ לטווח שאפשר לחשב" : undefined}
        styles={isChanged ? { input: { borderColor: "var(--almond)" } } : undefined}
      />
    );
  }

  function setMixCount(rooms: Rooms, value: Num) {
    setForm((f) => ({ ...f, mixMode: "manual", mix: { ...f.mix, [rooms]: value } }));
  }

  return (
    <Paper id="scenario" withBorder p="md" mt="lg" style={{ scrollMarginTop: "5rem" }}>
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="xs">
        <div style={{ flex: "1 1 16rem", minWidth: 0 }}>
          <Text fw={700} size="lg">מחשבון תרחיש</Text>
          <Text size="sm" c="dimmed">
            הנתונים של התיק הם ברירת המחדל. שנה ערכים או בחר תמהיל, והדוח מחושב מחדש — הרווח אחרי היטל, השורות
            והתמהיל. החישוב בשרת, באותו מודל של התיק, ושום דבר אינו נשמר.
          </Text>
        </div>
        <Group gap="xs" wrap="wrap">
          <Button variant="default" size="sm" onClick={reset} disabled={untouched && !result && !error}>
            חזרה לברירת המחדל
          </Button>
          <Button size="sm" onClick={() => compute(body)} loading={busy} disabled={hasInvalid}>חשב</Button>
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="sm" verticalSpacing="sm" mt="md">
        <div>
          <Select
            label={<Group gap={6} wrap="nowrap" component="span">שטח לבנייה{form.areaBasis !== defaults.areaBasis && <Badge size="xs" color="almond">שונה</Badge>}</Group>}
            description="400% הוא תקרה בחוק ולא זכות"
            data={areaOptions}
            value={form.areaBasis}
            onChange={(v) => v && set("areaBasis", v as AreaBasis)}
            allowDeselect={false}
          />
          {form.areaBasis === "custom" && (
            <div style={{ marginTop: ".5rem" }}>
              {numberField("customArea", "מ״ר לבנייה", {
                hint: cap ? `עד ${sqm(cap)} — תקרת החוק` : undefined, thousands: true, placeholder: "לדוגמה 3,000",
              })}
            </div>
          )}
        </div>
        {numberField("salePrice", "מחיר מכירה למ״ר (כולל מע״מ)", { suffix: " ₪", thousands: true, step: 500 })}
        {numberField("constructionCost", "עלות בנייה למ״ר", { suffix: " ₪", thousands: true, step: 100 })}
        {numberField("compensation", "תוספת מ״ר לכל דירה קיימת", { suffix: " מ״ר", decimals: true })}
        {numberField("existingPrice", "מחיר מ״ר של דירה קיימת", {
          suffix: " ₪", thousands: true, step: 500,
          placeholder: "אין מספיק עסקאות", hint: num(defaults.existingPrice) === null
            ? "אין ברירת מחדל — בלי מחיר אין אומדן השבחה" : undefined,
        })}
        {numberField("targetPct", "רווח יזמי מזערי (%)", { suffix: "%", decimals: true })}
        {numberField("financePct", "מימון (% מהעלויות)", { suffix: "%", decimals: true, step: 0.5 })}
        {numberField("unitArea", "שטח דירה קיימת ממוצע", { suffix: " מ״ר", decimals: true })}
        {numberField("betterment", "השבחה (לפי שומה או הערכה שלך)", {
          thousands: true, step: 100_000,
          placeholder: econ.after_levy ? `האומדן שלנו: ${ilsApprox(econ.after_levy.betterment_ils)}` : "אין אומדן",
          hint: "ריק = אומדן בשיטת היזם. מספר כאן מחליף אותו",
        })}
      </SimpleGrid>

      <Paper bg="var(--ground-2)" p="sm" mt="md">
        <Group justify="space-between" wrap="wrap" gap="xs">
          <Group gap={6}>
            <Text fw={600} size="sm">תמהיל דירות ליזם</Text>
            {form.mixMode !== "none" && <Badge size="xs" color="almond">{form.mixMode === "optimize" ? "מיטבי" : "שונה"}</Badge>}
          </Group>
          <Group gap="xs">
            <Button size="xs" variant="light" onClick={() => set("mixMode", "optimize")}
                    disabled={form.mixMode === "optimize"}>מלא תמהיל מיטבי</Button>
            {form.mixMode !== "none" && (
              <Button size="xs" variant="subtle" color="gray"
                      onClick={() => setForm((f) => ({ ...f, mixMode: "none", mix: { 3: "", 4: "", 5: "" } }))}>
                בלי תמהיל
              </Button>
            )}
          </Group>
        </Group>
        <SimpleGrid cols={3} spacing="xs" mt="xs">
          {ROOMS.map((rooms) => (
            <NumberInput key={rooms} label={`${rooms} חד׳ · ${ROOM_SQM[rooms]} מ״ר`} placeholder="0"
                         value={form.mix[rooms]} onChange={(v) => setMixCount(rooms, v)}
                         min={0} max={1000} step={1} allowDecimal={false} allowNegative={false} />
          ))}
        </SimpleGrid>
        <Text size="xs" c="dimmed" mt={6}>
          {form.mixMode === "none"
            ? "בלי תמהיל, כל השטח שנשאר ליזם נמכר לפי מחיר המכירה. עם תמהיל, נמכרות רק הדירות שבו."
            : form.mixMode === "optimize"
              ? "התמהיל הרווחי ביותר שעומד במגבלות מדיניות הרצליה, על השטח, המחיר והתמורה שבחרת."
              : "תמהיל שהזנת. תמהיל שאינו נכנס בשטח ליזם נדחה; חריגה ממגבלות המדיניות מוצגת כאזהרה."}
          {" "}גודלי הדירות הם הנחת מודל.
        </Text>
      </Paper>

      {error && <Alert color="brick" mt="md" title="התרחיש לא חושב">{error}</Alert>}

      {s && !error && (
        <div style={{ marginTop: "1rem", opacity: stale ? 0.55 : 1, transition: "opacity .15s" }} aria-busy={stale}>
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text fw={700}>{result && resultKey !== "{}" ? "התוצאה · התרחיש שלך" : "התוצאה · ברירת המחדל של התיק"}</Text>
            {stale && <Text size="sm" c="dimmed">{hasInvalid ? "יש ערך מחוץ לטווח — התוצאה אינה מעודכנת" : "מחשב…"}</Text>}
          </Group>
          <StatStrip cols={{ base: 1, sm: 3 }}>
            <Stat
              label={after
                ? <WithTerm id="profit_after_levy">{after.manual ? "רווח אחרי היטל (לפי ההשבחה שהזנת)" : "רווח יזמי אחרי היטל השבחה (אומדן)"}</WithTerm>
                : "רווח · לפני היטל השבחה"}
              value={ilsApprox(s.projected_profit_ils)}
              tone={s.projected_profit_ils < 0 ? "bad" : undefined}
            />
            <Stat
              label={<WithTerm id="profit_on_cost">רווח על העלות</WithTerm>}
              value={pct(s.profit_margin_on_cost_ratio)}
              tone={s.meets_developer_target ? "ok" : "warn"}
              hint={after && !after.manual ? `טווח ${pct(after.margin_low)}–${pct(after.margin_high)} לפי טווח ההיטל` : undefined}
              hintTone="neutral"
            />
            <Stat
              label="שטח לבנייה"
              value={shown.buildable_area_sqm != null ? sqm(shown.buildable_area_sqm) : "—"}
              hint={`שטח ליזם ${sqm(s.developer_allocation_sqm)}`}
              hintTone="neutral"
            />
          </StatStrip>

          {shown.profit_verdict && (
            <Text size="sm" fw={600} mt="sm" className={s.meets_developer_target ? "text-ok" : "text-warn"}>
              {shown.profit_verdict}
            </Text>
          )}

          {shown.unit_mix?.summary && (
            <Paper bg="var(--ground-2)" p="sm" mt="sm">
              <Text size="sm">{shown.unit_mix.summary}</Text>
              {!!shown.unit_mix.policy_warnings?.length && (
                <List size="sm" spacing={2} mt={4} className="text-warn">
                  {shown.unit_mix.policy_warnings.map((w) => <List.Item key={w}>{w}</List.Item>)}
                </List>
              )}
            </Paper>
          )}

          {shown.caveats.filter((c) => c.id === "area_basis_developer").map((c) => (
            <Text key={c.id} size="sm" c="dimmed" mt="sm">{c.text}</Text>
          ))}

          {shown.cost_rows && (
            <Table mt="sm">
              <Table.Tbody>
                {shown.cost_rows.map((row) => (
                  <Table.Tr key={row.id}>
                    <Table.Td><WithRowInfo row={row} /></Table.Td>
                    <Table.Td ta="end" className={`num ${row.value_ils < 0 ? "text-bad" : "text-ok"}`} fw={600}
                              style={{ whiteSpace: "nowrap" }}>
                      {ilsApprox(row.value_ils)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                <Table.Tr>
                  <Table.Td fw={700}>{after ? "רווח אחרי היטל" : "רווח"}</Table.Td>
                  <Table.Td ta="end" fw={700} style={{ whiteSpace: "nowrap" }}
                            className={`num ${s.projected_profit_ils < 0 ? "text-bad" : "text-ok"}`}>
                    {ilsApprox(s.projected_profit_ils)}
                  </Table.Td>
                </Table.Tr>
                {shown.betterment && (
                  <Table.Tr>
                    <Table.Td colSpan={2} className="text-warn" fw={600}>{shown.betterment.summary}</Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          )}

          {result && resultKey !== "{}" && (
            <div style={{ marginTop: ".8rem" }}>
              <Text size="sm" fw={600}>ערכים ששינית</Text>
              <ChangedList items={result.overrides_applied} />
            </div>
          )}
        </div>
      )}

      <Group gap="xs" mt="md" wrap="wrap">
        <Button variant="default" size="sm" leftSection={<IconFile size={15} />} loading={downloading === "pdf"}
                disabled={hasInvalid || downloading !== null} onClick={() => download("pdf")}>
          PDF של התרחיש
        </Button>
        <Button variant="default" size="sm" leftSection={<IconSheet size={15} />} loading={downloading === "xlsx"}
                disabled={hasInvalid || downloading !== null} onClick={() => download("xlsx")}>
          Excel של התרחיש
        </Button>
        {untouched && <Text size="xs" c="dimmed">בלי שינויים הקובץ הוא התיק, עם כותרת ״תרחיש מותאם״.</Text>}
      </Group>
    </Paper>
  );
}
