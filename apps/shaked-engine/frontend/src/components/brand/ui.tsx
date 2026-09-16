"use client";

import { Badge, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import Link from "next/link";
import type { ReactNode } from "react";
import { ASSESSMENT_STATUS, ASSUMPTION_STATUS, GATE_STATUS, type Tone } from "@/lib/labels";
import { IconChevronRight } from "./icons";

/** הטון (labels.ts) → צבע ב-Mantine. `Badge variant="light"` מוצמד ל-`--ok-*` ב-MantineShell. */
export const TONE_COLOR: Record<Tone, string> = { ok: "moss", warn: "almond", bad: "brick", neutral: "gray" };

export function StatusBadge({ tone, children, size = "sm" }: { tone: Tone; children: ReactNode; size?: "xs" | "sm" | "md" }) {
  return <Badge color={TONE_COLOR[tone]} size={size}>{children}</Badge>;
}

const fallback = (raw: string) => ({ label: raw, tone: "neutral" as Tone });
export const gateBadge = (statusKey: string) => { const s = GATE_STATUS[statusKey] ?? fallback(statusKey); return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>; };
export const assumptionBadge = (statusKey: string) => { const s = ASSUMPTION_STATUS[statusKey] ?? fallback(statusKey); return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>; };
export const assessmentBadge = (statusKey: string) => { const s = ASSESSMENT_STATUS[statusKey] ?? fallback(statusKey); return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>; };

/** כותרת מסך: קישור חזרה, שורת מבוא, כותרת, שורת פרטים, ופעולות בצד. */
export function PageHeader({ back, eyebrow, title, meta, actions }: {
  back?: { href: string; label: string };
  eyebrow?: string;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header style={{ marginBottom: "1.2rem" }}>
      {back && (
        <Link href={back.href} className="text-link" style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: ".85rem", fontWeight: 600, color: "var(--muted)", marginBottom: ".6rem" }}>
          <IconChevronRight size={14} />{back.label}
        </Link>
      )}
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
        <div style={{ flex: "1 1 16rem", minWidth: 0 }}>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <Title order={1} style={{ margin: 0 }}>{title}</Title>
          {meta && <Text c="dimmed" mt={4} size="sm">{meta}</Text>}
        </div>
        {actions && <Group gap="xs" wrap="wrap">{actions}</Group>}
      </Group>
    </header>
  );
}

/** קטע בתיק: כותרת, הערת מבוא מהשרת, ותוכן. */
export function Section({ id, title, note, children, actions }: { id?: string; title: string; note?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <Paper component="section" id={id} p="lg" mb="md">
      <Group justify="space-between" align="flex-start" mb={note ? 4 : "sm"}>
        <Title order={2} style={{ fontSize: "1.1rem" }}>{title}</Title>
        {actions}
      </Group>
      {note && <Text c="dimmed" size="sm" mb="sm">{note}</Text>}
      {children}
    </Paper>
  );
}

/** מספר אחד עם תווית, ורמז אופציונלי בצבע. */
export function Stat({ label, value, hint, hintTone = "warn", tone }: { label: ReactNode; value: ReactNode; hint?: ReactNode; hintTone?: Tone; tone?: Tone }) {
  const toneVar = tone ? { ok: "var(--ok-fg)", warn: "var(--warn-fg)", bad: "var(--bad-fg)", neutral: "var(--ink)" }[tone] : undefined;
  return (
    <Stack gap={2}>
      <span className="stat-label">{label}</span>
      <span className="stat-value num" style={toneVar ? { color: toneVar } : undefined}>{value}</span>
      {hint && <span className={`text-${hintTone}`} style={{ fontSize: ".78rem", fontWeight: 600 }}>{hint}</span>}
    </Stack>
  );
}

export function StatStrip({ children, cols }: { children: ReactNode; cols?: { base?: number; sm?: number; md?: number } }) {
  return <SimpleGrid cols={cols ?? { base: 2, sm: 3, md: 4 }} spacing="lg" verticalSpacing="md" mt="md">{children}</SimpleGrid>;
}
