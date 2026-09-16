"use client";

import { useEffect, useState } from "react";

interface Props {
  /** התקדמות הסריקה, אם כבר יש: כמה חלקות נבדקו וכמה תיקים נמצאו. */
  progress?: { checked: number; found: number } | null;
}

/** נקודות ״הזדמנות״ שהראדר חושף בסיבובו. מיקום באחוזים מתוך ריבוע 200×200. */
const BLIPS: { x: number; y: number; delay: number }[] = [
  { x: 132, y: 62, delay: 0.55 },
  { x: 74, y: 128, delay: 1.9 },
  { x: 148, y: 138, delay: 2.75 },
  { x: 62, y: 76, delay: 3.6 },
];

/**
 * חלון טעינה מלא-מסך בזמן חיפוש. הסריקה עוברת חלקה-חלקה בארכיון העירוני
 * ולכן עשויה להימשך דקות — בלי מסך שמראה שמשהו קורה, המשתמש לוחץ שוב או
 * סוגר את הדף. הראדר הוא המטאפורה הישירה: ״מחפשים הזדמנויות באזור״.
 */
export default function SearchingOverlay({ progress }: Props) {
  // ‏המונה מופיע רק אחרי שהשרת החזיר משהו — לפני כן ״0 חלקות״ נראה כתקלה.
  const hasProgress = !!progress && progress.checked > 0;
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-live="polite"
      aria-labelledby="searching-title"
      className="sk-searching"
    >
      <div className="card sk-searching-card">
        <svg className="sk-radar" viewBox="0 0 200 200" width="200" height="200" aria-hidden="true">
          <defs>
            {/* קרן הסריקה: דהייה מכתום מלא לשקוף לאורך רבע סיבוב */}
            <linearGradient id="sk-radar-sweep" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--almond)" stopOpacity="0.55" />
              <stop offset="100%" stopColor="var(--almond)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <circle cx="100" cy="100" r="96" className="sk-radar-ring" />
          <circle cx="100" cy="100" r="64" className="sk-radar-ring" />
          <circle cx="100" cy="100" r="32" className="sk-radar-ring" />
          <line x1="100" y1="4" x2="100" y2="196" className="sk-radar-ring" />
          <line x1="4" y1="100" x2="196" y2="100" className="sk-radar-ring" />

          <g className="sk-radar-arm">
            {/* גזרה של 90°: מהמרכז ימינה, נסגרת למעלה */}
            <path d="M100 100 L196 100 A96 96 0 0 0 100 4 Z" fill="url(#sk-radar-sweep)" />
            <line x1="100" y1="100" x2="196" y2="100" stroke="var(--almond)" strokeWidth="2" strokeLinecap="round" />
          </g>

          {BLIPS.map((b) => (
            <g key={`${b.x}-${b.y}`} className="sk-radar-blip" style={{ animationDelay: `${b.delay}s` }}>
              <circle cx={b.x} cy={b.y} r="4" fill="var(--almond)" />
              <circle cx={b.x} cy={b.y} r="4" fill="none" stroke="var(--almond)" strokeWidth="1.5" className="sk-radar-blip-ring" style={{ animationDelay: `${b.delay}s` }} />
            </g>
          ))}
          <circle cx="100" cy="100" r="3" fill="var(--ink)" />
        </svg>

        <h2 id="searching-title" className="sk-searching-title">מחפשים הזדמנויות באזור</h2>
        <p className="sk-searching-note">פעולה זו עשויה להימשך מספר דקות</p>
        <p className="sk-searching-progress" aria-live="polite">
          {hasProgress
            ? <>נבדקו <strong>{progress!.checked}</strong> חלקות · נמצאו <strong>{progress!.found}</strong> תיקים</>
            : "סורקים את הארכיון העירוני חלקה אחר חלקה"}
        </p>
        <p className="sk-searching-timer" dir="ltr">{mm}:{ss}</p>
      </div>
    </div>
  );
}
