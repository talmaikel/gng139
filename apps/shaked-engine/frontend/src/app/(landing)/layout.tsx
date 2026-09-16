import "@mantine/carousel/styles.css";
import "./landing.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Shaked Engine · shakdan",
  description: "המנוע של shakdan מאתר כל מגרש בהרצליה שעומד בתנאי הסף של חלופת שקד, ומגיש לכל אחד תיק מוכן ליזם.",
};

// Theme, fonts and Mantine core styles come from the root layout.
export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
