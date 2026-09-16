"use client";

import { useState } from "react";
import type { Preference, SearchOptions, SortField } from "@/lib/api";

const FIELD_LABEL: Record<SortField, string> = {
  parcel_area: "שטח המגרש",
  units: "מספר הדירות הקיים",
  floors: "מספר הקומות המותר",
  cap_400: 'תקרת 400% במ"ר',
};

const MANDATORY: { key: keyof SearchOptions; label: string; unit: string }[] = [
  { key: "minAreaSqm", label: "שטח מגרש", unit: 'מ"ר' },
  { key: "minUnits", label: "דירות קיימות", unit: "יח״ד" },
  { key: "minFloors", label: "קומות מותרות", unit: "" },
  { key: "minCap400Sqm", label: "תקרת 400%", unit: 'מ"ר' },
];

/** עד שלוש. מעבר לכך הסדר מפסיק להיות מובן למי שהגדיר אותו, וזה גם מה
 *  שהשרת אוכף — בקשה עם ארבע חוזרת 422. */
const MAX_PREFERENCES = 3;

interface Props {
  value: SearchOptions;
  onChange: (next: SearchOptions) => void;
  /** בלי `onApply` אין כפתור ״החל״: בסריקה (S2) התנאים נשלחים עם ״חפש״. */
  onApply?: () => void;
  disabled?: boolean;
}

/**
 * תנאי חובה וסדר העדפות, ובמכוון בשני אזורים נפרדים במסך.
 *
 * ‏SEL-01 מונה ״כללים, תנאי חובה וסדר העדיפויות״ כשלושה דברים. ההפרדה
 * אינה קוסמטית: **תנאי חובה מוציא מועמד מהרשימה, והעדפה רק מזיזה אותו
 * בה.** יזם שיחשוב שמינימום שטח הוא ״העדפה חזקה״ יקבל רשימה שיש בה
 * מגרשים שאינם רלוונטיים לו, ויסיק שהסינון לא עובד.
 *
 * הסדר לקסיקוגרפי ולא משוקלל — ‏PRD 4.2 דורש סדר מפורש ולא ניקוד סמוי,
 * ולכן ההעדפה הראשונה מכריעה, והשנייה נכנסת רק בשוויון.
 */
export default function SearchControls({ value, onChange, onApply, disabled }: Props) {
  const prefs = value.preferences ?? [];
  const used = new Set(prefs.map((p) => p.field));
  const available = (Object.keys(FIELD_LABEL) as SortField[]).filter((f) => !used.has(f));

  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  function setPrefs(next: Preference[]) {
    onChange({ ...value, preferences: next });
  }

  /** מזיזה את הפריט מ-from ל-to, בכל מרחק — לא רק בין שכנים.
   *  משמשת גם את הגרירה וגם את כפתורי ↑/↓, כדי ששני הנתיבים ייצרו
   *  תמיד את אותה תוצאה. */
  function moveTo(from: number, to: number) {
    if (to < 0 || to >= prefs.length || from === to) return;
    const next = [...prefs];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setPrefs(next);
  }

  return (
    <div className="card" style={{ padding: "1rem 1.1rem", display: "grid", gap: "1rem" }}>
      <section>
        <h3 style={{ margin: "0 0 .1rem", fontSize: ".95rem" }}>תנאי חובה</h3>
        <p className="text-muted" style={{ margin: "0 0 .55rem", fontSize: ".82rem" }}>
          מועמד שאינו עומד בהם אינו מוצג כלל. ערך לא ידוע אינו עומד בתנאי מזערי.
        </p>
        <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap", alignItems: "center" }}>
          {MANDATORY.map(({ key, label, unit }) => (
            <label key={key} style={{ display: "flex", alignItems: "center", gap: ".35rem", fontSize: ".85rem" }}>
              {label} ≥
              <input
                type="number"
                min={0}
                value={(value[key] as number | undefined) ?? ""}
                placeholder="—"
                onChange={(e) =>
                  onChange({ ...value, [key]: e.target.value === "" ? undefined : Number(e.target.value) })
                }
                style={{ width: 92, padding: ".3rem .45rem", fontSize: ".85rem" }}
              />
              <span className="text-muted">{unit}</span>
            </label>
          ))}

          <label style={{ display: "flex", alignItems: "center", gap: ".35rem", fontSize: ".85rem" }}>
            <input
              type="checkbox"
              checked={value.certainFloorsOnly ?? false}
              onChange={(e) => onChange({ ...value, certainFloorsOnly: e.target.checked })}
              style={{ width: "auto" }}
            />
            רק קביעת קומות ודאית
          </label>
        </div>
      </section>

      <section>
        <h3 style={{ margin: "0 0 .1rem", fontSize: ".95rem" }}>סדר העדפות</h3>
        <p className="text-muted" style={{ margin: "0 0 .55rem", fontSize: ".82rem" }}>
          הראשונה מכריעה; הבאה נכנסת רק בשוויון. לא ניקוד משוקלל — סדר מפורש.
        </p>

        <div style={{ display: "grid", gap: ".4rem" }}>
          {prefs.map((pref, i) => (
            <div
              key={pref.field}
              draggable
              onDragStart={() => setDraggedIndex(i)}
              onDragEnd={() => setDraggedIndex(null)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (draggedIndex !== null) moveTo(draggedIndex, i);
                setDraggedIndex(null);
              }}
              style={{
                display: "flex", gap: ".4rem", alignItems: "center",
                opacity: draggedIndex === i ? 0.5 : 1,
              }}
            >
              <span
                aria-hidden
                title="גרור לסידור"
                style={{ cursor: "grab", color: "var(--faint)", fontSize: ".9rem", width: "1.1rem", textAlign: "center" }}
              >
                ⠿
              </span>
              <span className="text-muted" style={{ fontSize: ".82rem", width: "1.1rem" }}>{i + 1}.</span>
              <strong style={{ fontSize: ".87rem", minWidth: "10.5rem" }}>{FIELD_LABEL[pref.field]}</strong>
              <button
                onClick={() =>
                  setPrefs(prefs.map((p, j) =>
                    j === i ? { ...p, direction: p.direction === "desc" ? "asc" : "desc" } : p))
                }
                className="btn-secondary btn-sm"
              >
                {pref.direction === "desc" ? "מהגדול לקטן" : "מהקטן לגדול"}
              </button>
              <button
                onClick={() => moveTo(i, i - 1)}
                disabled={i === 0}
                aria-label="העלה"
                className="btn-secondary btn-sm"
              >
                ↑
              </button>
              <button
                onClick={() => moveTo(i, i + 1)}
                disabled={i === prefs.length - 1}
                aria-label="הורד"
                className="btn-secondary btn-sm"
              >
                ↓
              </button>
              <button
                onClick={() => setPrefs(prefs.filter((_, j) => j !== i))}
                className="btn-ghost btn-sm text-bad"
              >
                הסר
              </button>
            </div>
          ))}

          {prefs.length === 0 && (
            <span className="text-muted" style={{ fontSize: ".85rem" }}>
              לא הוגדרו העדפות — הסדר יהיה לפי מזהה יציב.
            </span>
          )}
        </div>

        {prefs.length < MAX_PREFERENCES && available.length > 0 && (
          <div style={{ display: "flex", gap: ".4rem", marginTop: ".55rem", flexWrap: "wrap" }}>
            {available.map((field) => (
              <button
                key={field}
                onClick={() => setPrefs([...prefs, { field, direction: "desc" }])}
                className="btn-secondary btn-sm"
                style={{ borderStyle: "dashed" }}
              >
                + {FIELD_LABEL[field]}
              </button>
            ))}
          </div>
        )}
      </section>

      <div style={{ display: "flex", gap: ".6rem", alignItems: "center" }}>
        {onApply && (
          <button onClick={onApply} disabled={disabled}>
            החל על האזור המסומן
          </button>
        )}
        <button className="btn-ghost" onClick={() => onChange({})}>
          אפס הכל
        </button>
      </div>
    </div>
  );
}
