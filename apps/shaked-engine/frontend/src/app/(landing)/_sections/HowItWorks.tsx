"use client";

import { Carousel, type Embla } from "@mantine/carousel";
import { ActionIcon } from "@mantine/core";
import { useCallback, useEffect, useRef, useState } from "react";

const THRESHOLDS = ["מועד ההיתר", "70% מגורים", "בוצע חיזוק", "מספר מבנים", "יוזמה קיימת"];
const PREFERENCES = ["גודל מגרש", "קומות", "רוחב רחוב", "מספר דירות", "שכונה", "תקרת זכויות"];

const Arrow = ({ d }: { d: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);

function Pic({ step }: { step: number }) {
  const font = "var(--font-plex), sans-serif";
  if (step === 1) {
    const rows: [string, "ok" | "ask" | "no"][] = [["מועד ההיתר לפני 2005", "ok"], ["70% שימוש למגורים", "ok"], ["רוחב רחוב ≥ 8 מ׳", "ask"], ["בוצע חיזוק", "no"]];
    return (
      <svg viewBox="0 0 360 200" aria-hidden>
        <rect width="360" height="200" fill="#FFFFFF" />
        {rows.map(([t, s], k) => {
          const y = 37 + k * 36;
          return (
            <g key={t}>
              <text x="330" y={y + 5} textAnchor="end" fontFamily={font} fontSize="13" fill="#13161E">{t}</text>
              <circle cx="40" cy={y} r="11" fill={s === "ok" ? "#DCEFE3" : s === "ask" ? "#FDEEE3" : "#EBEDF1"} />
              {s === "ok" && <path d={`M34 ${y}l4 4 8-8`} stroke="#1F5A3C" strokeWidth="2.5" fill="none" />}
              {s === "ask" && <text x="40" y={y + 5} textAnchor="middle" fontSize="14" fontWeight="700" fill="#C96F33">?</text>}
              {s === "no" && <path d={`M35 ${y - 5}l10 10M45 ${y - 5}l-10 10`} stroke="#8B9099" strokeWidth="2.5" />}
            </g>
          );
        })}
        <rect x="20" y="172" width="320" height="1" fill="#DDE0E6" />
        <text x="330" y="190" textAnchor="end" fontFamily="var(--font-plex-mono), monospace" fontSize="10" fill="#8B9099">מקור: היתר · GovMap · מדידה</text>
      </svg>
    );
  }
  if (step === 2) {
    const lines: [string, string, boolean?][] = [["תקרת 400%", "11,300 מ״ר"], ["שטח מכירה", "8,814 מ״ר"], ["רווח יזמי", "14.7%", true], ["כדאי כל עוד ההיטל מתחת ל־", "14,862 ₪/מ״ר"]];
    return (
      <svg viewBox="0 0 360 200" aria-hidden>
        <rect width="360" height="200" fill="#FFFFFF" />
        <text x="330" y="36" textAnchor="end" fontFamily={font} fontSize="15" fontWeight="700" fill="#13161E">אלוף יגאל אלון 40</text>
        <text x="330" y="54" textAnchor="end" fontFamily="var(--font-plex-mono), monospace" fontSize="10" fill="#8B9099">6537 / 120</text>
        {lines.map(([k, v, strong], i) => (
          <g key={k}>
            <text x="330" y={90 + i * 28} textAnchor="end" fontFamily={font} fontSize="11" fill="#5B6068">{k}</text>
            <text x="30" y={90 + i * 28} fontFamily="var(--font-plex-mono), monospace" fontSize="12" fontWeight={strong ? 700 : 400} fill={strong ? "#C96F33" : "#13161E"}>{v}</text>
            {i < 3 && <path d={`M30 ${98 + i * 28}h300`} stroke="#ECEEF2" />}
          </g>
        ))}
      </svg>
    );
  }
  if (step === 3) {
    return (
      <svg viewBox="0 0 360 200" aria-hidden>
        <rect width="360" height="200" fill="#EEF0F3" />
        <rect x="60" y="30" width="110" height="140" rx="4" fill="#fff" stroke="#DDE0E6" />
        <text x="115" y="60" textAnchor="middle" fontFamily={font} fontSize="18" fontWeight="700" fill="#13161E">PDF</text>
        <g stroke="#DDE0E6" strokeWidth="3" strokeLinecap="round"><path d="M80 85h70M80 100h70M80 115h50M80 140h70" /></g>
        <rect x="190" y="30" width="110" height="140" rx="4" fill="#fff" stroke="#DDE0E6" />
        <text x="245" y="60" textAnchor="middle" fontFamily={font} fontSize="18" fontWeight="700" fill="#13161E">XLSX</text>
        <g stroke="#DDE0E6"><path d="M205 80h80M205 100h80M205 120h80M205 140h80M245 70v80" /></g>
        <rect x="247" y="102" width="36" height="16" fill="#E8894A" fillOpacity=".25" stroke="#E8894A" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 360 200" aria-hidden>
      <rect width="360" height="200" fill="#EEF0F3" />
      <g stroke="#D9DDE3" strokeWidth="2"><path d="M0 60h360M0 120h360M90 0v200M200 0v200M290 0v200" /></g>
      <path d="M70 40 L250 55 L280 150 L120 170 Z" fill="#E8894A" fillOpacity=".18" stroke="#E8894A" strokeWidth="3" strokeDasharray="8 6" />
      <g fill="#E8894A"><rect x="110" y="70" width="22" height="16" rx="2" /><rect x="150" y="90" width="18" height="18" rx="2" /><rect x="200" y="75" width="24" height="14" rx="2" /><rect x="180" y="120" width="20" height="20" rx="2" /><rect x="235" y="110" width="16" height="22" rx="2" /></g>
      {[[70, 40], [250, 55], [280, 150], [120, 170]].map(([x, y]) => <circle key={`${x}`} cx={x} cy={y} r="6" fill="#13161E" />)}
    </svg>
  );
}

const STEPS = [
  { title: "מסמנים אזור על המפה", body: <p>פוליגון חופשי, רחוב אחד, או כל העיר. כל חלקה בתוך האזור נכנסת לבדיקה, בלי לבחור ידנית.</p>, out: <><b>רשימת חלקות</b> עם גוש/חלקה, שטח וקומות</> },
  {
    title: "המנוע מסנן: תנאי הסף, ומה שחשוב לך",
    body: (
      <>
        <p>קודם כל תנאי סף של חלופת שקד נבדק בנפרד: מה עבר, מה נפל, ומה עוד לא ידוע. <strong>ואז מסננים לפי הפרמטרים שלך</strong>, כדי שברשימה יישארו רק המגרשים שמתאימים לפרויקט.</p>
        <div className="sk-chip-group"><span>תנאי הסף</span><div className="sk-filters" style={{ padding: 0 }}>{THRESHOLDS.map((t) => <span key={t}>{t}</span>)}</div></div>
        <div className="sk-chip-group"><span>סינון נוסף</span><div className="sk-filters" style={{ padding: 0 }}>{PREFERENCES.map((t) => <span key={t} style={{ background: "var(--almond-soft)", borderColor: "transparent", color: "var(--almond-deep)", fontWeight: 600 }}>{t}</span>)}</div></div>
      </>
    ),
    out: <><b>מצב לכל חלקה</b>, עם הנימוק</>,
  },
  { title: "פותחים תיק לחלקה", body: <p>הזכויות לפי התכנית, תקרת 400%, לוח הדירות הקיימות, ותרחיש כלכלי שכל הנחה בו גלויה. <strong>כל התוכניות</strong>: כמה תרחישים לאותה חלקה, זה לצד זה.</p>, out: <><b>רווח יזמי</b> ותקרת היטל השבחה</> },
  { title: "מייצאים ומעבירים הלאה", body: <p>PDF לוועדה, אקסל למחלקת הכלכלה. אותם מספרים בדיוק כמו במסך, ואפשר לשנות מחיר מכירה בתא אחד ולראות את הרווח זז.</p>, out: <><b>מקור ומועד</b> לכל מספר בתיק</> },
];

export function HowItWorks() {
  const [embla, setEmbla] = useState<Embla | null>(null);
  const [active, setActive] = useState(0);
  const viewport = useRef<HTMLDivElement>(null);
  const dots = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!embla) return;
    const onSelect = () => setActive(embla.selectedScrollSnap());
    embla.on("select", onSelect);
    return () => { embla.off("select", onSelect); };
  }, [embla]);

  // At either end, a click nudges the slides toward where the user tried to go and springs back.
  const bounce = useCallback((dir: 1 | -1) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const px = dir * 34; // RTL: "next" lies to the left, so the content moves right
    viewport.current?.animate(
      [{ transform: "translateX(0)" }, { transform: `translateX(${px}px)`, offset: 0.28 }, { transform: `translateX(${-px * 0.35}px)`, offset: 0.6 }, { transform: `translateX(${px * 0.1}px)`, offset: 0.82 }, { transform: "translateX(0)" }],
      { duration: 620, easing: "ease-out" },
    );
    const dot = dots.current?.children[active] as HTMLElement | undefined;
    dot?.animate(
      [{ transform: "translateX(0) scale(1)" }, { transform: `translateX(${-dir * 7}px) scale(1.25,.8)`, offset: 0.3 }, { transform: `translateX(${dir * 3}px) scale(.92,1.08)`, offset: 0.62 }, { transform: "translateX(0) scale(1)" }],
      { duration: 560, easing: "ease-out" },
    );
  }, [active]);

  const go = (i: number) => {
    if (!embla) return;
    if (i < 0) return bounce(-1);
    if (i >= STEPS.length) return bounce(1);
    embla.scrollTo(i);
  };

  return (
    <div className="sk-car" data-bf="">
      <div ref={viewport}>
        <Carousel withControls={false} withIndicators={false} loop={false} slideGap={0} slideSize="100%" getEmblaApi={setEmbla} aria-roledescription="carousel">
          {STEPS.map((s, i) => (
            <Carousel.Slide key={s.title} aria-label={`שלב ${i + 1} מתוך ${STEPS.length}`}>
              <div className="sk-slide">
                <div>
                  <div className="sk-num"><b>{i + 1}</b><small>שלב {i + 1} מתוך {STEPS.length}</small></div>
                  <h3>{s.title}</h3>
                  {s.body}
                  <div className="sk-out">מקבלים: {s.out}</div>
                </div>
                <div className="sk-pic"><Pic step={i} /></div>
              </div>
            </Carousel.Slide>
          ))}
        </Carousel>
      </div>
      <div className="sk-car-nav">
        <ActionIcon variant="default" size={40} radius="xl" aria-label="השלב הקודם" onClick={() => go(active - 1)} style={{ opacity: active === 0 ? 0.45 : 1 }}>
          <Arrow d="M9 6l6 6-6 6" />
        </ActionIcon>
        <div className="sk-dots" ref={dots}>
          {STEPS.map((s, i) => (
            <button key={s.title} type="button" className="sk-dot" data-active={i === active} aria-label={`שלב ${i + 1}`} onClick={() => go(i)} />
          ))}
        </div>
        <ActionIcon variant="default" size={40} radius="xl" aria-label="השלב הבא" onClick={() => go(active + 1)} style={{ opacity: active === STEPS.length - 1 ? 0.45 : 1 }}>
          <Arrow d="M15 6l-6 6 6 6" />
        </ActionIcon>
      </div>
    </div>
  );
}
