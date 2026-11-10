"use client";

import { TextInput, Textarea, Tooltip } from "@mantine/core";
import Link from "next/link";
import { useEffect, useState } from "react";
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

/** Section title block, numbered like the sheets of a zoning plan. */
function SheetHead({ n, label, id, title, lead, oneLine }: { n: number; label: string; id: string; title: React.ReactNode; lead: string; oneLine?: boolean }) {
  return (
    <header className="sk-head" data-bf="">
      <p className="sk-index"><span className="sk-mono">{String(n).padStart(2, "0")}</span>{label}</p>
      <h2 id={id}>{title}</h2>
      <p className={oneLine ? "sk-lead sk-one-line" : "sk-lead"}>{lead}</p>
    </header>
  );
}

/** Natural scrolling. The header tracks the section in view, and each section reveals once. */
function useSections() {
  const [active, setActive] = useState("top");
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const els = PAGES.map((p) => document.getElementById(p.id)).filter(Boolean) as HTMLElement[];
    els.forEach((s) => s.querySelectorAll("[data-bf]").forEach((n, k) => (n as HTMLElement).style.setProperty("--i", String(k))));

    const reveal = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("sk-in"); reveal.unobserve(e.target); } });
    }, { threshold: 0.12 });
    els.forEach((s) => reveal.observe(s));

    const spy = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) setActive(e.target.id); });
    }, { rootMargin: "-45% 0px -50% 0px" });
    els.forEach((s) => spy.observe(s));

    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { reveal.disconnect(); spy.disconnect(); window.removeEventListener("scroll", onScroll); };
  }, []);

  return { active, scrolled };
}

export function LandingPage() {
  const { active, scrolled } = useSections();
  const navLink = (id: string, label: string) => (
    <li><a href={`#${id}`} aria-current={active === id ? "true" : undefined}>{label}</a></li>
  );

  return (
    <div className="sk" dir="rtl" lang="he">
      {/* The reveal waits for JavaScript; without it, show everything. */}
      <noscript><style>{".sk [data-bf]{opacity:1;transform:none}"}</style></noscript>
      <a className="sk-skip" href="#product">דילוג לתוכן</a>

      <header className={scrolled ? "sk-header is-scrolled" : "sk-header"}>
        <nav className="sk-wrap sk-nav" aria-label="ראשי">
          <Link href="/" className="sk-lockup">
            <img src="/brand/shakdan-lockup.svg" alt="shakdan" width={155} height={38} />
            <small>מודיעין להתחדשות עירונית</small>
          </Link>
          <ul>
            {navLink("how", "איך זה עובד")}
            {navLink("why", "למה שקדן")}
            {navLink("contact", "צרו קשר")}
          </ul>
          <div className="sk-nav-actions">
            <Link href="/login">האזור האישי</Link>
            <a className="sk-btn sk-primary sk-small" href="#contact">בקשת הדגמה</a>
          </div>
        </nav>
      </header>

      <section className="sk-section sk-first" id="top" aria-label="פתיחה">
        <div className="sk-hero">
          <img src="/brand/herzliya.jpg" alt="הרצליה ממבט על: שכונות מגורים, ומאחוריהן הים" />
          <div className="sk-wrap sk-hero-inner">
            <span className="sk-eyebrow" data-bf="">חלופת שקד · הרצליה</span>
            <h1 data-bf=""><bdi>Shaked Engine</bdi></h1>
            <p className="sk-hero-lead" data-bf="">המנוע של shakdan מאתר כל מגרש בהרצליה שעומד בתנאי הסף של חלופת שקד, ומגיש לכל אחד תיק מוכן ליזם.</p>
            <div className="sk-ctas" data-bf="">
              <a className="sk-btn sk-primary" href="#contact">בקשת הדגמה</a>
              <Link className="sk-btn sk-ghost" href="/login">כניסה לאזור האישי</Link>
            </div>
          </div>
          <div className="sk-wrap">
            <p className="sk-meta" data-bf="">
              <span><i className="sk-mono">A</i><b>כל חלקה</b> בעיר</span>
              <span><i className="sk-mono">B</i><b>תנאי הסף</b>, אחד אחד</span>
              <span><i className="sk-mono">C</i><b>מקור</b> לכל מספר</span>
            </p>
          </div>
          <a className="sk-credit" href="https://commons.wikimedia.org/wiki/File:%D7%A6%D7%99%D7%9C%D7%95%D7%9D_%D7%9E%D7%94%D7%90%D7%95%D7%99%D7%A8_%D7%A9%D7%9C_%D7%94%D7%A8%D7%A6%D7%9C%D7%99%D7%94_23.jpg" target="_blank" rel="noopener noreferrer">
            Photo: Lev Tsimbler · CC BY-SA 4.0
          </a>
        </div>
      </section>

      <section className="sk-section" id="product" aria-labelledby="product-title">
        <div className="sk-wrap">
          <SheetHead n={1} label="המוצר" id="product-title" title={<>כל ההזדמנויות.<br />במחשב ובטלפון.</>} lead="מסמנים אזור, ורואים מיד אילו חלקות בו עומדות בתנאים ואילו לא, ולמה. כל שורה ברשימה מובילה לתיק." />
          <Devices />
        </div>
      </section>

      <section className="sk-section sk-paper" id="how" aria-labelledby="how-title">
        <div className="sk-wrap">
          <SheetHead n={2} label="איך זה עובד" id="how-title" title="איך זה עובד" lead="ארבעה שלבים. בכל אחד רואים מה נכנס, מה יוצא, ועל סמך מה." />
          <HowItWorks />
        </div>
      </section>

      <section className="sk-section" id="why" aria-labelledby="why-title">
        <div className="sk-wrap">
          <SheetHead n={3} label="למה שקדן" id="why-title" title="למה שקדן" lead="כל מה שצריך כדי להחליט על מגרש, במקום אחד." />
          <WhyFlow />
          <ol className="sk-reasons">
            <li className="sk-reason" data-bf=""><span className="sk-mono">3.1</span><h3>נוחות</h3><p>מסמנים אזור ומקבלים רשימה. בלי לעבור בין GovMap, תב״עות, ארכיון ההנדסה וגיליונות אקסל.</p></li>
            <li className="sk-reason" data-bf=""><span className="sk-mono">3.2</span><h3>חיסכון בזמן</h3><p>איסוף המסמכים והבדיקה הראשונית כבר נעשו. פותחים את התיק ומתחילים מהשאלה אם להתקדם.</p></li>
            <li className="sk-reason" data-bf=""><span className="sk-mono">3.3</span><h3>כל המידע ברגע אחד, אצלך ביד</h3><p>זכויות, תנאי הסף, תרחיש כלכלי והמקורות. בתיק אחד, במחשב ובטלפון.</p></li>
          </ol>
        </div>
      </section>

      <section className="sk-section sk-contact" id="contact" aria-labelledby="contact-title">
        <div className="sk-band">
          <div className="sk-wrap sk-cta" data-bf="">
            <div>
              <p className="sk-index sk-index-dark"><span className="sk-mono">04</span>צרו קשר</p>
              <h2 id="contact-title">רוצים לראות את <bdi style={{ whiteSpace: "nowrap" }}>Shaked Engine</bdi> על הרצליה?</h2>
              <p>הדגמה של 30 דקות על חלקות אמיתיות, עם תיק אחד מלא לדוגמה.</p>
            </div>
            <a className="sk-btn sk-primary" href="#contact-form">בקשת הדגמה</a>
          </div>
        </div>

        <div className="sk-wrap">
          <div className="sk-contact-grid">
            <div className="sk-contact-info" data-bf="">
              <h3>צרו קשר</h3>
              <p>נחזור אליכם תוך יום עסקים.</p>
              <dl className="sk-lines">
                {["דוא״ל", "טלפון", "וואטסאפ", "כתובת"].map((k) => <div key={k}><dt>{k}</dt><dd className="sk-tbd">ימולא בהמשך</dd></div>)}
              </dl>
            </div>
            <form className="sk-form" id="contact-form" data-bf="" onSubmit={(e) => e.preventDefault()}>
              <div className="sk-form-row">
                <TextInput id="cf-name" label="שם" />
                <TextInput id="cf-company" label="חברה" />
              </div>
              <div className="sk-form-row">
                <TextInput id="cf-email" label="דוא״ל" type="email" dir="ltr" />
                <TextInput id="cf-phone" label="טלפון" type="tel" dir="ltr" />
              </div>
              <Textarea id="cf-message" label="במה נוכל לעזור?" autosize minRows={3} />
              <Tooltip label="הטופס יחובר לתיבת הדואר של החברה בהמשך" position="top-start">
                <span style={{ justifySelf: "start" }}>
                  <button className="sk-btn sk-primary" type="submit" disabled aria-disabled>שליחה</button>
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
  );
}
