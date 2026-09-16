"use client";

import { ActionIcon, Anchor, Popover, Text } from "@mantine/core";
import { createContext, useContext, type ReactNode } from "react";
import type { GlossaryEntry, TermId } from "@/lib/api";
import { IconHelp } from "@/components/brand/icons";

/** ‏W4 · המילון של התיק. הנוסח בשרת (`glossary.py`) — כאן רק איך פותחים אותו.
 *
 *  השותפים שאלו מה זה ״מכריע״ ומה זו ״תקרת הקטגוריה״. ההסבר לא נכתב במסך:
 *  נוסח מקומי היה נפרד בשקט מה-PDF ומהאקסל, כמו התוויות לפני A8. */
export const GlossaryContext = createContext<Record<string, GlossaryEntry>>({});

/** ״?״ קטן שפותח את ההסבר בלחיצה — לא בריחוף, כי בטלפון אין ריחוף. */
export function Term({ id }: { id: TermId }) {
  const entry = useContext(GlossaryContext)[id];
  // מזהה שאינו במילון נופל ב-`test_glossary.py`; כאן פשוט לא מציגים ״?״ ריק.
  if (!entry) return null;
  return (
    <Popover
      width={320}
      position="bottom"
      withArrow
      shadow="md"
      trapFocus
      returnFocus
    >
      <Popover.Target>
        {/* ‏24px ללחיצה באצבע, ו-my שלילי כדי שהשורה של התווית לא תגבה בגללו. */}
        <ActionIcon
          variant="subtle"
          color="gray"
          size={24}
          my={-4}
          radius="xl"
          aria-label={`הסבר: ${entry.term}`}
          style={{ verticalAlign: "middle", flex: "none" }}
        >
          <IconHelp size={14} />
        </ActionIcon>
      </Popover.Target>
      {/* ‏`width` של Mantine עובר דרך rem() ושובר min()/calc(), ולכן הגבול לטלפון כאן. */}
      <Popover.Dropdown style={{ maxWidth: "calc(100vw - 2rem)" }}>
        <Text size="sm" fw={600}>{entry.term}</Text>
        <Text size="sm" mt={4} style={{ lineHeight: 1.55 }}>{entry.short}</Text>
        {entry.source_url && (
          <Anchor href={entry.source_url} target="_blank" rel="noreferrer" size="sm" c="almond.7" mt={6} display="inline-block">
            מקור
          </Anchor>
        )}
      </Popover.Dropdown>
    </Popover>
  );
}

/** תווית עם ״?״ אחריה. זרימה רגילה ולא flex: בתוך flex תג כמו ״נותב למתחמים״
 *  מתכווץ לשלוש נקודות בתא צר, ותווית ארוכה צריכה לשבור שורה כרגיל. */
export function WithTerm({ id, children }: { id: TermId; children: ReactNode }) {
  return (
    <span>
      {children}
      {"\u00a0"}
      <Term id={id} />
    </span>
  );
}
