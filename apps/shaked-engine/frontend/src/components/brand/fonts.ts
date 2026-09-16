import { IBM_Plex_Mono, IBM_Plex_Sans_Hebrew } from "next/font/google";

export const plex = IBM_Plex_Sans_Hebrew({ subsets: ["hebrew", "latin"], weight: ["400", "600", "700"] });
export const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["500"] });

// Declared on :root, because Mantine resolves its font variables there.
export const fontRootCss = `:root{--font-plex:${plex.style.fontFamily};--font-plex-mono:${plexMono.style.fontFamily}}`;
