"use client";

import type { ScanConditions } from "@/lib/api";

type NumericKey = "minAreaSqm" | "maxUnits";

// ‏בלי ״רווח יזמי״ (טל, 16.09): הסף נשאר של השרת — הרווח היזמי המזערי בספריית ההנחות.
const FIELDS: { key: NumericKey; label: string; op: string; unit: string }[] = [
  { key: "minAreaSqm", label: "שטח מגרש", op: "≥", unit: 'מ"ר' },
  { key: "maxUnits", label: "דירות קיימות", op: "≤", unit: "יח״ד" },
];

interface Props {
  value: ScanConditions;
  onChange: (next: ScanConditions) => void;
}

/** כמה תנאים הלקוח הגדיר — למונה שעל הכפתור. */
export function countConditions(c: ScanConditions): number {
  return FIELDS.filter(({ key }) => c[key] !== undefined).length + (c.includeRightsRequest ? 1 : 0);
}

/**
 * ‏W6 · התנאים של הלקוח בסריקה (בועז, 16.09): שלושה, ובלי סדר העדפות.
 *
 * **לא `SearchControls`:** זה נשאר למסך המנהל, עם תנאי הצוות וסדר ההעדפות.
 * כאן הסדר אינו בידי הלקוח — השרת מוסר מוכנות קודם, ובתוכן הרווחיות ביותר.
 */
export default function ScanConditionsControls({ value, onChange }: Props) {
  return (
    <div className="card" style={{ padding: "1rem 1.1rem", display: "grid", gap: "1rem" }}>
      <section>
        <h3 style={{ margin: "0 0 .1rem", fontSize: ".95rem" }}>תנאים</h3>
        <p className="text-muted" style={{ margin: "0 0 .55rem", fontSize: ".82rem" }}>
          חלקה שאינה עומדת בהם לא תימסר. מבין אלה שעומדים, תקבל את הרווחיות ביותר.
        </p>
        <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center" }}>
          {FIELDS.map(({ key, label, op, unit }) => (
            <label key={key} style={{ display: "flex", alignItems: "center", gap: ".35rem", fontSize: ".85rem" }}>
              {label} {op}
              <input
                type="number"
                min={0}
                value={value[key] ?? ""}
                placeholder="—"
                onChange={(e) =>
                  onChange({ ...value, [key]: e.target.value === "" ? undefined : Number(e.target.value) })
                }
                style={{ width: 92, padding: ".3rem .45rem", fontSize: ".85rem" }}
              />
              <span className="text-muted">{unit}</span>
            </label>
          ))}
        </div>
      </section>

      <label style={{ display: "flex", alignItems: "flex-start", gap: ".45rem", fontSize: ".85rem" }}>
        <input
          type="checkbox"
          checked={value.includeRightsRequest ?? false}
          onChange={(e) => onChange({ ...value, includeRightsRequest: e.target.checked })}
          style={{ width: "auto", marginTop: ".2rem" }}
        />
        <span>
          כלול חלקות שכלכליות רק עם הגדלת זכויות
          <span className="text-muted" style={{ display: "block", fontSize: ".8rem" }}>
            יימסרו אחרי החלקות הכלכליות. אם באזור אין אף חלקה כלכלית, נבקש את אישורך לפני שמחייבים.
          </span>
        </span>
      </label>

      <div>
        <button className="btn-ghost" onClick={() => onChange({})}>
          אפס הכל
        </button>
      </div>
    </div>
  );
}
