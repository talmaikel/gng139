"use client";

import { ActionIcon, Stepper, TextInput, Textarea, Tooltip } from "@mantine/core";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Devices } from "./Devices";
import { HowItWorks } from "./HowItWorks";
import { WhyFlow } from "./WhyFlow";

const PAGES = [
  { id: "top", label: "פתיחה" },
  { id: "product", label: "המוצר" },
  { id: "how", label: "איך זה עובד" },
  { id: "why", label: "למה שקדן" },
  { id: "contact", label: "צרו קשר" },
];

const Chevron = ({ d }: { d: string }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
);

/** Page-by-page navigation: wheel, arrow keys and the side rail fade between full-screen pages. */
function usePaging(root: React.RefObject<HTMLDivElement>) {
  const [page, setPage] = useState(0);
  const busy = useRef(false);
  const lastWheel = useRef(0);

  const sections = useCallback(() => PAGES.map((p) => document.getElementById(p.id)).filter(Boolean) as HTMLElement[], []);

  const enter = (el: HTMLElement) => { el.classList.remove("sk-enter"); void el.offsetWidth; el.classList.add("sk-enter"); };

  const goTo = useCallback((i: number) => {
    const els = sections();
    const target = Math.max(0, Math.min(els.length - 1, i));
    if (busy.current || !root.current) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    busy.current = true;
    root.current.classList.add("sk-fading");
    window.setTimeout(() => {
      els[target].scrollIntoView({ behavior: "instant" as ScrollBehavior, block: "start" });
      setPage(target);
      enter(els[target]);
      root.current?.classList.remove("sk-fading");
      window.setTimeout(() => { busy.current = false; }, 250);
    }, reduce ? 0 : 340);
  }, [root, sections]);

  useEffect(() => {
    const els = sections();
    if (els[0]) enter(els[0]);
    // Blur Fade: stagger what enters on each page
    els.forEach((s) => s.querySelectorAll("[data-bf]").forEach((n, k) => (n as HTMLElement).style.setProperty("--i", String(k))));

    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setPage(els.indexOf(e.target as HTMLElement)); });
    }, { threshold: 0.55 });
    els.forEach((s) => io.observe(s));

    // Paging takes over the wheel only where a mouse drives a wide screen; touch keeps natural scrolling.
    const desktop = window.matchMedia("(min-width: 1100px) and (pointer: fine)");
    const onWheel = (e: WheelEvent) => {
      if (!desktop.matches || (e.target as HTMLElement).closest("textarea, .mantine-Carousel-root")) return;
      e.preventDefault();
      const now = Date.now();
      if (now - lastWheel.current < 750 || Math.abs(e.deltaY) < 8) return;
      lastWheel.current = now;
      const current = els.findIndex((s) => Math.abs(s.getBoundingClientRect().top) < window.innerHeight / 2);
      goTo((current < 0 ? 0 : current) + (e.deltaY > 0 ? 1 : -1));
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, [role=combobox]")) return;
      const current = els.findIndex((s) => Math.abs(s.getBoundingClientRect().top) < window.innerHeight / 2);
      if (e.key === "PageDown" || (e.key === "ArrowDown" && desktop.matches)) { e.preventDefault(); goTo(current + 1); }
      if (e.key === "PageUp" || (e.key === "ArrowUp" && desktop.matches)) { e.preventDefault(); goTo(current - 1); }
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("keydown", onKey);
    return () => { io.disconnect(); window.removeEventListener("wheel", onWheel); window.removeEventListener("keydown", onKey); };
  }, [goTo, sections]);

  return { page, goTo };
}

export function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  const { page, goTo } = usePaging(root);

  return (
    <>
      <nav className="sk-rail" aria-label="דפדוף בין העמודים">
        <div className="sk-rail-arrows">
          <ActionIcon variant="default" radius="xl" size="md" aria-label="העמוד הקודם" disabled={page === 0} onClick={() => goTo(page - 1)}><Chevron d="M6 15l6-6 6 6" /></ActionIcon>
          <ActionIcon variant="default" radius="xl" size="md" aria-label="העמוד הבא" disabled={page === PAGES.length - 1} onClick={() => goTo(page + 1)}><Chevron d="M6 9l6 6 6-6" /></ActionIcon>
        </div>
        <Stepper active={page} onStepClick={goTo} orientation="vertical" size="xs" iconSize={22} allowNextStepsSelect>
          {PAGES.map((p) => <Stepper.Step key={p.id} label={p.label} />)}
        </Stepper>
      </nav>

      <div className="sk" dir="rtl" lang="he" ref={root}>
        <section className="sk-page sk-first" id="top" aria-label="פתיחה">
          <div className="sk-wrap">
            <nav className="sk-nav">
              <Link href="/" className="sk-lockup">
                <img src="/brand/shakdan-lockup.svg" alt="shakdan" width={155} height={38} />
                <small>מודיעין להתחדשות עירונית</small>
              </Link>
              <ul>
                <li><a href="#how">איך זה עובד</a></li>
                <li><a href="#why">למה שקדן</a></li>
                <li><a href="#contact">צרו קשר</a></li>
              </ul>
              <div className="sk-nav-actions">
                <Link href="/login">האזור האישי</Link>
                <a className="sk-btn sk-primary sk-small" href="#contact">בקשת הדגמה</a>
              </div>
            </nav>
          </div>
          <div className="sk-hero">
            <img src="/brand/herzliya.jpg" alt="הרצליה ממבט על: שכונות מגורים, ומאחוריהן הים" />
            <div className="sk-wrap sk-hero-inner">
              <span className="sk-eyebrow" data-bf="">חלופת שקד · הרצליה</span>
              <h1 data-bf=""><bdi>Shaked Engine</bdi></h1>
              <p data-bf="">המנוע של shakdan מאתר כל מגרש בהרצליה שעומד בתנאי הסף של חלופת שקד, ומגיש לכל אחד תיק מוכן ליזם.</p>
              <div className="sk-ctas" data-bf="">
                <a className="sk-btn sk-primary" href="#contact">בקשת הדגמה</a>
                <Link className="sk-btn sk-ghost" href="/login">כניסה לאזור האישי</Link>
              </div>
              <p className="sk-meta" data-bf=""><span><b>כל חלקה</b> בעיר</span><span><b>תנאי הסף</b>, אחד אחד</span><span><b>מקור</b> לכל מספר</span></p>
            </div>
            <a className="sk-credit" href="https://commons.wikimedia.org/wiki/File:%D7%A6%D7%99%D7%9C%D7%95%D7%9D_%D7%9E%D7%94%D7%90%D7%95%D7%99%D7%A8_%D7%A9%D7%9C_%D7%94%D7%A8%D7%A6%D7%9C%D7%99%D7%94_23.jpg" target="_blank" rel="noopener noreferrer">
              Photo: Lev Tsimbler · CC BY-SA 4.0
            </a>
          </div>
        </section>

        <section className="sk-page" id="product" aria-labelledby="product-title">
          <div className="sk-wrap" style={{ paddingBlock: "2.4rem 1rem" }}>
            <div className="sk-head">
              <h2 id="product-title" data-bf="">כל ההזדמנויות.<br />במחשב ובטלפון.</h2>
              <p className="sk-one-line" data-bf="">מסמנים אזור, ורואים מיד אילו חלקות בו עומדות בתנאים ואילו לא, ולמה. כל שורה ברשימה מובילה לתיק.</p>
            </div>
            <Devices />
          </div>
        </section>

        <section className="sk-page" id="how" aria-labelledby="how-title">
          <div className="sk-wrap" style={{ paddingBlock: "2.4rem" }}>
            <div className="sk-head">
              <h2 id="how-title" data-bf="">איך זה עובד</h2>
              <p data-bf="">ארבעה שלבים. בכל אחד רואים מה נכנס, מה יוצא, ועל סמך מה.</p>
            </div>
            <HowItWorks />
          </div>
        </section>

        <section className="sk-page" id="why" aria-labelledby="why-title">
          <div className="sk-wrap" style={{ paddingBlock: "2.4rem" }}>
            <div className="sk-head">
              <h2 id="why-title" data-bf="">למה שקדן</h2>
              <p data-bf="">כל מה שצריך כדי להחליט על מגרש, במקום אחד.</p>
            </div>
            <WhyFlow />
            <div className="sk-reasons">
              <div className="sk-reason" data-bf=""><span className="ic"><svg viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5" /></svg></span><h3>נוחות</h3><p>מסמנים אזור ומקבלים רשימה. בלי לעבור בין GovMap, תב״עות, ארכיון ההנדסה וגיליונות אקסל.</p></div>
              <div className="sk-reason" data-bf=""><span className="ic"><svg viewBox="0 0 24 24"><circle cx="12" cy="13" r="8" /><path d="M12 9v4l2.5 2.5M9 2h6" /></svg></span><h3>חיסכון בזמן</h3><p>איסוף המסמכים והבדיקה הראשונית כבר נעשו. פותחים את התיק ומתחילים מהשאלה אם להתקדם.</p></div>
              <div className="sk-reason" data-bf=""><span className="ic"><svg viewBox="0 0 24 24"><rect x="6" y="2.5" width="12" height="19" rx="2.5" /><path d="M10.5 18.5h3" /></svg></span><h3>כל המידע ברגע אחד, אצלך ביד</h3><p>זכויות, תנאי הסף, תרחיש כלכלי והמקורות. בתיק אחד, במחשב ובטלפון.</p></div>
            </div>
          </div>
        </section>

        <section className="sk-page" id="contact" aria-labelledby="contact-title">
          <div className="sk-wrap" style={{ paddingBlock: "2.4rem 0" }}>
            <div className="sk-cta" data-bf="">
              <span className="sk-beam" />
              <div>
                <h2 id="contact-title">רוצים לראות את <bdi style={{ whiteSpace: "nowrap" }}>Shaked Engine</bdi> על הרצליה?</h2>
                <p>הדגמה של 30 דקות על חלקות אמיתיות, עם תיק אחד מלא לדוגמה.</p>
              </div>
              <a className="sk-btn sk-primary" href="#contact-form">בקשת הדגמה</a>
            </div>
            <div className="sk-contact-grid">
              <div className="sk-box" data-bf="">
                <h3>צרו קשר</h3>
                <p>נחזור אליכם תוך יום עסקים.</p>
                <ul className="sk-lines">
                  {["דוא״ל", "טלפון", "וואטסאפ", "כתובת"].map((k) => <li key={k}><span>{k}</span><span className="sk-tbd">ימולא בהמשך</span></li>)}
                </ul>
              </div>
              <form className="sk-box" id="contact-form" data-bf="" onSubmit={(e) => e.preventDefault()} style={{ display: "grid", gap: "0.8rem" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
                  <TextInput id="cf-name" label="שם" />
                  <TextInput id="cf-company" label="חברה" />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
                  <TextInput id="cf-email" label="דוא״ל" type="email" dir="ltr" />
                  <TextInput id="cf-phone" label="טלפון" type="tel" dir="ltr" />
                </div>
                <Textarea id="cf-message" label="במה נוכל לעזור?" autosize minRows={3} />
                <Tooltip label="הטופס יחובר לתיבת הדואר של החברה בהמשך" position="top-start">
                  <span style={{ justifySelf: "start" }}>
                    <button className="sk-btn sk-primary" type="submit" disabled aria-disabled style={{ opacity: 0.7, cursor: "not-allowed" }}>שליחה</button>
                  </span>
                </Tooltip>
              </form>
            </div>

            <footer className="sk-footer">
              <div className="brand">
                <img src="/brand/shakdan-lockup.svg" alt="shakdan" width={122} height={30} />
                <p><bdi>shakdan</bdi> · מודיעין להתחדשות עירונית.<br />המוצר: <bdi>Shaked Engine</bdi>.</p>
              </div>
              <nav className="sk-cols" aria-label="קישורים">
                <div><h4>המוצר</h4><a href="#top">Shaked Engine</a><a href="#how">איך זה עובד</a><a href="#contact">מחירים</a><a href="#contact">בקשת הדגמה</a></div>
                <div><h4>החברה</h4><a href="#">אודות</a><a href="#">הצוות</a><a href="#">קריירה</a><a href="#">עדכונים</a></div>
                <div><h4>עזרה</h4><a href="#contact">צרו קשר</a><a href="#">שאלות נפוצות</a><a href="#">מדריך למשתמש</a><Link href="/login">כניסה ללקוחות</Link></div>
                <div><h4>משפטי</h4><a href="#">תנאי שימוש</a><a href="#">מדיניות פרטיות</a><a href="#">הצהרת נגישות</a><a href="#">קרדיטים</a></div>
              </nav>
              <div className="sk-bottom">
                <span>© shakdan 2026</span>
                <span>הנתונים ציבוריים. הסינון והתרחיש הכלכלי אינם ייעוץ משפטי או שמאי.</span>
              </div>
            </footer>
          </div>
        </section>
      </div>
    </>
  );
}
