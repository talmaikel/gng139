import "@mantine/core/styles.css";
import "@mantine/carousel/styles.css";
import "./landing.css";
import type { Metadata } from "next";
import { fontRootCss } from "@/components/brand/fonts";
import { MantineShell } from "@/components/brand/MantineShell";

export const metadata: Metadata = {
  title: "Shaked Engine · shakdan",
  description: "המנוע של shakdan מאתר כל מגרש בהרצליה שעומד בתנאי הסף של חלופת שקד, ומגיש לכל אחד תיק מוכן ליזם.",
};

export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <style>{fontRootCss}</style>
      <MantineShell>{children}</MantineShell>
    </>
  );
}
