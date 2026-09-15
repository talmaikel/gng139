"use client";

import { useEffect, useRef, useState } from "react";

// Animated Beam (magicui.design): the sources Shaked Engine reads, flowing into one dossier.
const SOURCES = ["GovMap · חלקות", "תב״עות ותכניות", "ארכיון ההנדסה", "עסקאות נדל״ן", "עלויות בנייה"];

export function WhyFlow() {
  const box = useRef<HTMLDivElement>(null);
  const engine = useRef<HTMLDivElement>(null);
  const out = useRef<HTMLDivElement>(null);
  const srcs = useRef<(HTMLDivElement | null)[]>([]);
  const [paths, setPaths] = useState<string[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0, narrow: false });

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight, narrow: el.clientWidth < 720 });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Once the nodes sit at their positions, trace a curve from each source into the engine, and one out.
  useEffect(() => {
    const el = box.current, e = engine.current, o = out.current;
    if (!el || !e || !o || !size.w) return;
    const fr = el.getBoundingClientRect();
    const rect = (n: Element) => {
      const r = n.getBoundingClientRect();
      return { l: r.left - fr.left, r: r.right - fr.left, cy: r.top - fr.top + r.height / 2 };
    };
    const E = rect(e), O = rect(o);
    const next = srcs.current.filter(Boolean).map((n) => {
      const S = rect(n!), mx = (S.l + E.r) / 2;
      return `M${S.l},${S.cy} C${mx},${S.cy} ${mx},${E.cy} ${E.r},${E.cy}`;
    });
    const mx = (E.l + O.r) / 2;
    next.push(`M${E.l},${E.cy} C${mx},${E.cy} ${mx},${O.cy} ${O.r},${O.cy}`);
    setPaths(next);
  }, [size]);

  const { w, h, narrow } = size;
  return (
    <div className="sk-flow" ref={box} data-bf="" role="img" aria-label="מקורות המידע נכנסים ל-Shaked Engine ויוצאים כתיק אחד ליזם">
      <svg className="sk-wires" aria-hidden>
        <defs>
          <linearGradient id="sk-pulse-grad" gradientUnits="userSpaceOnUse" x1={w} y1="0" x2="0" y2="0">
            <stop offset="0" stopColor="#F59A8C" /><stop offset="1" stopColor="#E8894A" />
          </linearGradient>
        </defs>
        {paths.map((d, k) => (
          <g key={d}>
            <path d={d} className="sk-wire" />
            <path d={d} className="sk-pulse" pathLength={100} style={{ animationDelay: `${k * -0.45}s` }} />
          </g>
        ))}
      </svg>
      {SOURCES.map((s, k) => (
        <div
          key={s}
          ref={(n) => { srcs.current[k] = n; }}
          className="sk-node"
          style={{ left: w * (narrow ? 0.74 : 0.82), top: h * (0.14 + k * 0.18) }}
        >
          <i />{s}
        </div>
      ))}
      <div ref={engine} className="sk-node sk-engine" style={{ left: w * (narrow ? 0.44 : 0.5), top: h / 2 }}>
        <img src="/brand/shakdan-lockup.svg" alt="" />
        <span>Shaked Engine</span>
      </div>
      <div ref={out} className="sk-node sk-out-node" style={{ left: w * (narrow ? 0.14 : 0.15), top: h / 2 }}>
        <b>תיק ליזם</b>
        <small>זכויות · תנאי הסף</small>
        <small>תרחיש כלכלי · מקורות</small>
      </div>
    </div>
  );
}
