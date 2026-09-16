// The product, drawn in the new language: web app in a MacBook, the iPhone app in front of it.
// Addresses and gush/helka are real Herzliya parcels; the screens are illustrations, not live data.

const ROWS = [
  { a: "אלוף יגאל אלון 40", g: "6537 / 120", f: "1,575 מ״ר · 7–9 קומות · 44 דירות", s: "ok", l: "ניתן למסירה" },
  { a: "הדר 19", g: "6538 / 476", f: "907 מ״ר · 8 קומות · 25 דירות", s: "ok", l: "ניתן למסירה" },
  { a: "אלוף יגאל אלון 6", g: "6529 / 43", f: "794 מ״ר · 7–9 קומות", s: "chk", l: "דורש אימות" },
  { a: "בוסל 12", g: "6530 / 284", f: "794 מ״ר · רוחב רחוב?", s: "chk", l: "דורש מדידה" },
  { a: "כבוש העבודה 18", g: "6536 / 386", f: "979 מ״ר · מסלול מתחמים", s: "no", l: "לא במסלול" },
];

const Search = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
  </svg>
);

export function Devices() {
  return (
    <div className="sk-screens" data-bf="">
      <div className="sk-laptop">
        <span className="sk-beam" style={{ inset: -11 }} />
        <div className="sk-bar" aria-hidden>
          <i style={{ background: "#FF5F57" }} /><i style={{ background: "#FEBC2E" }} /><i style={{ background: "#28C840" }} />
          <span>app.shakdan.co.il</span>
        </div>
        <div className="sk-app" role="img" aria-label="מסך המועמדים של Shaked Engine: רשימת חלקות ומפת הרצליה">
          <div className="sk-app-top">
            <img src="/brand/shakdan-lockup.svg" alt="" />
            <div className="sk-search"><Search />רחוב, כתובת, או גוש/חלקה</div>
            <div className="sk-tabs"><span className="on">חיפוש</span><span>המאגר שלי</span><span>תיקים</span></div>
            <div className="sk-me">ט</div>
          </div>
          <div className="sk-app-body">
            <div className="sk-list">
              <div className="sk-list-head"><b>מועמדים באזור</b><span>הסדר: לפי העדפות</span></div>
              <div className="sk-filters"><span className="on">עוברים סינון</span><span>דורשים אימות</span><span>7+ קומות</span><span>רוחב רחוב</span></div>
              {ROWS.map((r, i) => (
                <div key={r.g} className={`sk-card${i === 0 ? " sel" : ""}`}>
                  <b>{r.a}</b><span className="g">{r.g}</span><span className="f">{r.f}</span>
                  <span className={`sk-pill ${r.s}`}>{r.l}</span>
                </div>
              ))}
            </div>
            <div className="sk-map">
              <img src="/brand/herzliya-map.jpg" alt="" />
              <span className="sk-draw">✎ צייר אזור חיפוש</span>
              <div className="sk-popup">
                <b>אלוף יגאל אלון 40</b>
                <span className="sk-mono">גוש 6537 · חלקה 120</span>
                <div>תקרת 400%: 11,300 מ״ר</div>
                <div className="go">פתיחת התיק ←</div>
                <div className="alt">כל התוכניות · 3 תרחישים</div>
              </div>
              <div className="sk-legend">
                <span><i style={{ background: "var(--almond)" }} />עובר סינון</span>
                <span><i style={{ background: "#C9C1B3" }} />לא במסלול</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="sk-laptop-base" />
      <p className="sk-frame-cap">המפה: © OpenStreetMap contributors · חלקות מהרצליה</p>

      <div className="sk-phone" role="img" aria-label="אפליקציית Shaked Engine בטלפון">
        <div className="sk-ph">
          <div className="sk-ph-sb"><span>9:41</span><span>●●●</span></div>
          <div className="sk-ph-hd">
            <div><h4>הרצליה</h4><span>מועמדים · עודכן היום</span></div>
            <img src="/brand/shakdan-lockup.svg" alt="" />
          </div>
          <div className="sk-search"><Search />רחוב או גוש/חלקה</div>
          <div className="sk-ph-map"><img src="/brand/herzliya-map.jpg" alt="" /></div>
          <div className="sk-ph-sheet">
            <div className="grab" />
            {ROWS.slice(0, 4).map((r) => (
              <div key={r.g} className="sk-ph-row">
                <div><b>{r.a}</b><span className="g">{r.g}</span></div>
                <span className={`sk-pill ${r.s}`}>{r.l}</span>
              </div>
            ))}
          </div>
          <div className="sk-ph-tab">
            <div className="on"><svg viewBox="0 0 24 24"><path d="M12 21s7-6.2 7-11a7 7 0 0 0-14 0c0 4.8 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></svg>מפה</div>
            <div><svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h10" /></svg>רשימה</div>
            <div><svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>תיקים</div>
            <div><svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>חשבון</div>
          </div>
        </div>
      </div>
    </div>
  );
}
