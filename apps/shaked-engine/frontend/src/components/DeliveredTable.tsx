"use client";

import Link from "next/link";

import type { DeliveredOpportunity } from "@/lib/api";

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("he-IL", { day: "numeric", month: "short", year: "numeric" }) : "—";

/**
 * מאגר המסירות של החברה — ‏SEL-02: *״מגרש שכבר נמסר מוצג במאגר החברה
 * בלבד ואינו צורך זכאות נוספת״*.
 *
 * גרסת הכללים וגרסת הנתונים מוצגות כאן ולא נקברות, כי SEL-01 דורש
 * *״נשמרים גרסת הנתונים, גרסת הכללים והנימוק לכל בחירה״* — וזו התשובה
 * ללקוח ששואל בעוד חצי שנה למה דווקא המגרש הזה.
 */
export default function DeliveredTable({ rows }: { rows: DeliveredOpportunity[] }) {
  if (rows.length === 0) {
    return (
      <p style={{ color: "#6b655c", margin: 0 }}>
        טרם נמסרה הזדמנות. מסירה מתבצעת ממסך החיפוש, והיא מנכה זכאות אחת.
      </p>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>כתובת</th>
          <th>גוש / חלקה</th>
          <th>נמסר</th>
          <th>חויב</th>
          <th>גרסאות</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.delivery_id}>
            <td>{row.address}</td>
            <td>
              {row.block ?? "—"} / {row.parcel ?? "—"}
            </td>
            <td>{fmtDate(row.delivered_at)}</td>
            <td>{row.credits_charged === 0 ? "—" : `${row.credits_charged}`}</td>
            <td style={{ color: "#6b655c", fontSize: ".82rem" }}>
              {row.rules_version || "—"}
              {row.data_version ? ` · ${row.data_version}` : ""}
            </td>
            <td style={{ textAlign: "end" }}>
              <Link href={`/dossier/${row.opportunity_id}`}
                    style={{ color: "#1f6f4f", fontWeight: 600, fontSize: ".85rem" }}>
                פתח תיק ←
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
