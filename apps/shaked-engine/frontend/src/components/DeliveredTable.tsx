"use client";

import Link from "next/link";

import { isRightsRequest, type DeliveredOpportunity } from "@/lib/api";
import { fmtDate } from "@/lib/format";

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
      <p className="text-muted" style={{ margin: 0 }}>
        טרם נמסרה הזדמנות. מסירה מתבצעת ממסך החיפוש, והיא מנכה זכאות אחת.
      </p>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
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
            // ‏16.09 · תיק שכלכלי רק עם הגדלת זכויות: שורה צהובה ותגית
            <tr key={row.delivery_id} className={isRightsRequest(row) ? "is-rights" : undefined}>
              <td style={{ fontWeight: 600 }}>
                {row.address}
                {isRightsRequest(row) && (
                  <>{" "}<span className="pill rights">נדרשת הגדלת זכויות</span></>
                )}
              </td>
              <td className="mono" style={{ textAlign: "start" }}>
                {row.block ?? "—"} / {row.parcel ?? "—"}
              </td>
              <td>{fmtDate(row.delivered_at)}</td>
              <td className="num">{row.credits_charged === 0 ? "—" : `${row.credits_charged}`}</td>
              <td className="text-muted" style={{ fontSize: ".82rem" }}>
                {row.rules_version || "—"}
                {row.data_version ? ` · ${row.data_version}` : ""}
              </td>
              <td style={{ textAlign: "end" }}>
                <Link href={`/app/dossier/${row.opportunity_id}`} className="text-link" style={{ fontSize: ".85rem" }}>
                  פתח תיק ←
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
