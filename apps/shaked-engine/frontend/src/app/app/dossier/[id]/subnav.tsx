"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** מסכי התיק, כלשוניות. הנוכחית מסומנת בקו כתום, כמו בכותרת.
 *  ‏W8 · ״תמהיל ורווחיות״ אינו לשונית יותר: התמהיל הוא חלק מהדוח הכלכלי, במחשבון התרחיש. */
export function DossierSubNav({ id }: { id: string }) {
  const pathname = usePathname() ?? "";
  const tabs = [
    { href: `/app/dossier/${id}`, label: "תיק הזדמנות", active: pathname === `/app/dossier/${id}` },
    { href: `/app/dossier/${id}/units`, label: "אישור דירות קיימות", active: pathname.startsWith(`/app/dossier/${id}/units`) },
  ];
  return (
    <nav className="subnav" aria-label="חלקי התיק">
      {tabs.map((t) => (
        <Link key={t.href} href={t.href} data-active={t.active || undefined}>{t.label}</Link>
      ))}
    </nav>
  );
}
