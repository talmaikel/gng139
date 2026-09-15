import "@mantine/core/styles.css";
import "@mantine/carousel/styles.css";
import { IBM_Plex_Mono, IBM_Plex_Sans_Hebrew } from "next/font/google";
import { DesignProviders } from "./providers";

const plex = IBM_Plex_Sans_Hebrew({
  subsets: ["hebrew", "latin"],
  weight: ["400", "600", "700"],
});
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["500"] });

// Trial route for the Mantine design language. Scoped here so the rest of
// the app keeps its current styles until the language is approved.
export default function DesignLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* On :root, because Mantine resolves its font variables there. */}
      <style>{`:root{--font-plex:${plex.style.fontFamily};--font-plex-mono:${plexMono.style.fontFamily}}`}</style>
      <DesignProviders>{children}</DesignProviders>
    </>
  );
}
