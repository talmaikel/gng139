"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** שלושת מסכי התיק, כלשוניות. הנוכחית מסומנת בקו כתום, כמו בכותרת. */
export function DossierSubNav({ id }: { id: string }) {
  const pathname = usePathname() ?? "";
  const tabs = [
    { href: `/dossier/${id}`, label: "תיק הזדמנות", active: pathname === `/dossier/${id}` },
    { href: `/dossier/${id}/mix`, label: "תמהיל ורווחיות", active: pathname.startsWith(`/dossier/${id}/mix`) },
    { href: `/dossier/${id}/units`, label: "אישור דירות קיימות", active: pathname.startsWith(`/dossier/${id}/units`) },
  ];
  return (
    <nav className="subnav" aria-label="חלקי התיק">
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} data-active={t.active || undefined}>{t.label}</Link>
      ))}
    </nav>
  );
}
