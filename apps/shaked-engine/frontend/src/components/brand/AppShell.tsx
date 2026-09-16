"use client";

import { Menu } from "@mantine/core";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { clearToken, getMe, type Me } from "@/lib/api";
import { IconLogout, IconMenu } from "./icons";

const NAV = [
  { href: "/app", label: "סריקה", match: (p: string) => p === "/app" },
  { href: "/app#mine", label: "המאגר שלי", match: () => false },
];

/**
 * הכותרת של המוצר: הלוגו, הניווט, המשתמש, יציאה. אותה שורה בכל מסך.
 *
 * ‏**יציאה מובילה לדף הפתיחה ולא ל-/login**: ב-localhost מסך הכניסה מתחבר
 * מחדש לבד (dev-auto-login), ומי שיצא היה חוזר פנימה מיד.
 */
export function AppHeader() {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  function logout() {
    clearToken();
    router.replace("/");
  }

  const links = me?.is_superuser ? [...NAV, { href: "/admin", label: "ניהול", match: (p: string) => p.startsWith("/admin") }] : NAV;
  const initial = (me?.full_name || me?.email || "?").trim().charAt(0).toUpperCase();

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link href="/app" className="app-brand" aria-label="Shaked Engine">
          <img src="/brand/shakdan-lockup.svg" alt="shakdan" width={114} height={28} />
          <span>Shaked Engine</span>
        </Link>

        <nav className="app-nav" aria-label="ניווט">
          {links.map((l) => (
            <Link key={l.href} href={l.href} data-active={l.match(pathname) || undefined}>{l.label}</Link>
          ))}
        </nav>

        <div className="app-user">
          {me && (
            <>
              <span className="app-avatar" aria-hidden>{initial}</span>
              <span className="app-user-name">{me.full_name || me.email}</span>
            </>
          )}
          <button type="button" className="btn-ghost btn-sm app-logout" onClick={logout}>
            <IconLogout size={15} /> יציאה
          </button>
          <Menu shadow="md" width={200} position="bottom-end">
            <Menu.Target>
              <button type="button" className="btn-secondary btn-sm app-menu" aria-label="תפריט"><IconMenu size={16} /></button>
            </Menu.Target>
            <Menu.Dropdown>
              {links.map((l) => <Menu.Item key={l.href} component={Link} href={l.href}>{l.label}</Menu.Item>)}
              <Menu.Divider />
              <Menu.Item onClick={logout} leftSection={<IconLogout size={14} />}>יציאה</Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </div>
      </div>
    </header>
  );
}

/** כותרת + עמוד. `width` = רוחב התוכן; ברירת המחדל כמו `.page`. */
export function AppShell({ children, width }: { children: ReactNode; width?: number }) {
  return (
    <>
      <AppHeader />
      <main className="page" style={width ? { maxWidth: width } : undefined}>{children}</main>
    </>
  );
}
