import "@mantine/carousel/styles.css";
import "./landing.css";
import type { Metadata } from "next";

const SITE_URL = "https://gng139.online/";
const SITE_NAME = "שקדן";
const DESCRIPTION = "המנוע של shakdan מאתר כל מגרש בהרצליה שעומד בתנאי הסף של חלופת שקד, ומגיש לכל אחד תיק מוכן ליזם.";

export const metadata: Metadata = {
  title: "שקדן | איתור מגרשים להתחדשות עירונית",
  description: DESCRIPTION,
  alternates: { canonical: SITE_URL },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: "שקדן | איתור מגרשים להתחדשות עירונית",
    description: DESCRIPTION,
    locale: "he_IL",
  },
};

// Google reads the site name shown above search results from this block.
const websiteJsonLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: SITE_NAME,
  url: SITE_URL,
};

// Theme, fonts and Mantine core styles come from the root layout.
export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteJsonLd) }}
      />
      {children}
    </>
  );
}
