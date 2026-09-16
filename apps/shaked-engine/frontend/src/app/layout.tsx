import type { Metadata } from "next";
// Mantine first, then ours: on a tie our element rules win.
import "@mantine/core/styles.css";
import "@/styles/globals.css";
import { fontRootCss } from "@/components/brand/fonts";
import { MantineShell } from "@/components/brand/MantineShell";

export const metadata: Metadata = {
  title: "Shaked Engine · shakdan",
  description: "איתור מגרשים להתחדשות עירונית במסלול חלופת שקד, לחברות יזמיות",
  // Google Search Console ownership (HTML tag method).
  verification: { google: "PMkx6b-8Hl4Pi3CxSms9eg1PZIj8a3ckVkdM0QLDRIU" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body>
        {/* On :root, because Mantine resolves its font variables there. */}
        <style>{fontRootCss}</style>
        <MantineShell>{children}</MantineShell>
      </body>
    </html>
  );
}
