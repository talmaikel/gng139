"use client";

import { Alert, Button, Group, List, NumberInput, Paper, Table, Text } from "@mantine/core";
import Link from "next/link";
import { use, useState } from "react";
import { ils, sqm } from "@/lib/format";
import { PageHeader, Section, Stat, StatStrip } from "@/components/brand/ui";

interface Candidate {
  counts: Record<string, number>;
  total_new_units: number;
  developer_units: number;
  tenant_units: number;
  tenant_allocation_sqm: number;
  developer_used_sqm: number;
  developer_available_sqm: number;
  unused_developer_sqm: number;
  gross_developer_revenue_ils: number;
  projected_profit_ils: number;
  profit_margin_on_cost_ratio: number;
  meets_developer_target: boolean;
}

interface OptimizationResponse {
  address: string;
  planned_unit_mix: { rooms: number; area_sqm: number; units: number }[];
  planned_unit_mix_meta: {
    status: string;
    compensation_sqm_per_existing_unit: number;
    compensation_source: string;
    default_compensation_source: string | null;
    projected_profit_ils: number;
    profit_margin_on_cost_ratio: number;
    existing_units_basis: "confirmed_schedule" | "building_average";
    average_existing_unit_sqm: number;
    sale_price_per_sqm_ils: number;
    unit_area_assumption_source: string;
    warnings: string[];
  };
  optimization: {
    feasible: boolean;
    compensation_sqm_per_existing_unit: number;
    compensation_source: string;
    tenant_allocation_sqm: number;
    developer_available_sqm: number;
    candidates: Candidate[];
    warnings: string[];
  };
}

export default function UnitMixPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [compensation, setCompensation] = useState<string | number>("");
  const [result, setResult] = useState<OptimizationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function optimize() {
    setBusy(true);
    setError(null);
    try {
      const token = window.localStorage.getItem("shaked_token");
      const parsed = String(compensation).trim() === "" ? null : Number(compensation);
      if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) {
        setError("יש להזין תוספת שטח תקינה, או להשאיר ריק לברירת המחדל.");
        return;
      }
      const response = await fetch(`/api/v1/unit-mix/${id}/optimize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          compensation_sqm_per_existing_unit: parsed,
          persist: true,
        }),
      });
      if (!response.ok) {
        let message = "לא ניתן לחשב תמהיל כרגע.";
        try {
          const body = await response.json();
          if (typeof body?.detail === "string") message = body.detail;
        } catch { /* keep fallback */ }
        throw new Error(message);
      }
      setResult((await response.json()) as OptimizationResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : "לא ניתן לחשב תמהיל כרגע.");
    } finally {
      setBusy(false);
    }
  }

  const best = result?.optimization.candidates[0];

  return (
    <>
      <PageHeader
        back={{ href: `/dossier/${id}`, label: "חזרה לתיק" }}
        eyebrow="תיק הזדמנות · הרצליה"
        title="תמהיל דירות ורווחיות"
        meta="הזן את התמורה לבעלי הדירות. שינוי התמורה מחשב מחדש את השטח ליזם, התמהיל והרווח. אם השדה נשאר ריק, המערכת משתמשת בתמורת ברירת המחדל המסומנת כאומדן."
      />

      <Paper p="lg" mb="md">
        <Group align="flex-end" gap="sm" wrap="wrap">
          <NumberInput
            id="compensation"
            label="תוספת מ״ר לכל דירה קיימת"
            min={0} max={100} step={1}
            value={compensation}
            onChange={setCompensation}
            placeholder="ברירת מחדל מהשוק"
            w={220}
          />
          <Button onClick={optimize} loading={busy}>חשב תמהיל מיטבי</Button>
        </Group>
        <Text size="sm" c="dimmed" mt="sm">
          החישוב משתמש בזכויות, במחיר המכירה ובמודל של התיק. הדירות הקיימות לפי לוח מאושר, ואם אין — לפי ממוצע הבניין שבתיק.
        </Text>
      </Paper>

      {error && (
        <Alert color="brick" mb="md" title={error}>
          {error.includes("לוח דירות") && (
            <Link href={`/dossier/${id}/units`} className="text-link">פתח את מסך אישור הדירות הקיימות ←</Link>
          )}
        </Alert>
      )}

      {result && best && (
        <>
          <Section title="התמהיל המומלץ" note={result.address}>
            <StatStrip cols={{ base: 2, sm: 3 }}>
              <Stat label="תמורה שנלקחה בחשבון" value={sqm(result.optimization.compensation_sqm_per_existing_unit)} />
              <Stat label="שטח דירות בעלים" value={sqm(result.optimization.tenant_allocation_sqm)} />
              <Stat label="שטח זמין ליזם" value={sqm(result.optimization.developer_available_sqm)} />
              <Stat label="רווח לפי התמהיל" value={ils(best.projected_profit_ils)} />
              <Stat label="רווח על העלות" value={`${(best.profit_margin_on_cost_ratio * 100).toFixed(1)}%`} tone={best.meets_developer_target ? "ok" : "warn"} />
              <Stat label="שטח ליזם שלא נכנס לתמהיל" value={sqm(best.unused_developer_sqm)} />
            </StatStrip>

            <Table mt="md">
              <Table.Thead><Table.Tr><Table.Th>חדרים</Table.Th><Table.Th>שטח לדירה</Table.Th><Table.Th>מספר דירות יזם</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {result.planned_unit_mix.map((row) => (
                  <Table.Tr key={`${row.rooms}-${row.area_sqm}`}>
                    <Table.Td className="num">{row.rooms}</Table.Td><Table.Td className="num">{sqm(row.area_sqm)}</Table.Td><Table.Td className="num">{row.units}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Text size="sm" c="dimmed" mt="sm">
              כל הדירות לפי {ils(result.planned_unit_mix_meta.sale_price_per_sqm_ils)} למ״ר, מחיר המכירה שבתיק ·{" "}
              {result.planned_unit_mix_meta.existing_units_basis === "building_average"
                ? `דירה קיימת ממוצעת ${sqm(result.planned_unit_mix_meta.average_existing_unit_sqm)} (ממוצע הבניין, אומדן)`
                : "דירות קיימות לפי לוח מאושר"} ·
              התמהיל נשמר כאומדן ומוצג בתיק. הרווח בתיק אינו משתנה: הוא מוכר את כל השטח ליזם ומחושב בתמורת ברירת המחדל.
            </Text>
          </Section>

          {result.optimization.candidates.length > 1 && (
            <Section title="חלופות מובילות">
              <Table.ScrollContainer minWidth={640}>
                <Table>
                  <Table.Thead><Table.Tr><Table.Th>#</Table.Th><Table.Th>תמהיל</Table.Th><Table.Th>דירות יזם</Table.Th><Table.Th>רווח</Table.Th><Table.Th>רווח על העלות</Table.Th><Table.Th>שטח לא מנוצל</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {result.optimization.candidates.slice(0, 5).map((candidate, index) => (
                      <Table.Tr key={index} className={index === 0 ? "is-selected" : undefined}>
                        <Table.Td className="num">{index + 1}</Table.Td>
                        <Table.Td>{Object.entries(candidate.counts).map(([k, v]) => `${v} × ${k.replace("r", "")} חד׳`).join(" · ")}</Table.Td>
                        <Table.Td className="num">{candidate.developer_units}</Table.Td>
                        <Table.Td className="num">{ils(candidate.projected_profit_ils)}</Table.Td>
                        <Table.Td className={`num ${candidate.meets_developer_target ? "text-ok" : "text-warn"}`}>{(candidate.profit_margin_on_cost_ratio * 100).toFixed(1)}%</Table.Td>
                        <Table.Td className="num">{sqm(candidate.unused_developer_sqm)}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Section>
          )}

          <Section title="מה חשוב לדעת">
            <List size="sm" spacing={4}>
              <List.Item>ברירת המחדל לתמורה: {result.planned_unit_mix_meta.default_compensation_source ?? "אומדן גרסה"}.</List.Item>
              <List.Item>שטחי 3/4/5 חדרים הם הנחות מודל מסומנות, לא הוראה של עיריית הרצליה.</List.Item>
              {result.optimization.warnings.map((warning, i) => <List.Item key={i}>{warning}</List.Item>)}
            </List>
          </Section>
        </>
      )}
    </>
  );
}
