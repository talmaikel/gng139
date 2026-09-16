"use client";

import { ActionIcon, Popover, Text } from "@mantine/core";
import { IconHelp } from "@/components/brand/icons";
import type { CostRow } from "@/lib/dossier";

/** ‏W4 · נקודה 6: ״?״ ליד שורה בטבלת העלויות — מה השורה, הנוסחה ומאיפה הקלט. בלחיצה, כמו המונחים.
 *  משותף לתיק ולמחשבון התרחיש (W8), כדי ששתי הטבלאות יסבירו שורה באותה דרך. */
export function RowInfo({ row }: { row: CostRow }) {
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

export function WithRowInfo({ row }: { row: CostRow }) {
  return <span>{row.label}{" "}<RowInfo row={row} /></span>;
}
