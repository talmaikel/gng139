"use client";

import { createTheme, DirectionProvider, MantineProvider, type MantineColorsTuple } from "@mantine/core";

// Almond from the shakdan logo; index 5 is the brand #E8894A.
const almond: MantineColorsTuple = [
  "#FFF4EC", "#FDE6D6", "#F8C9A8", "#F3AB78", "#EE9458",
  "#E8894A", "#D9783A", "#C96F33", "#A85A28", "#86461E",
];

const theme = createTheme({
  colors: { almond },
  primaryColor: "almond",
  primaryShade: 5,
  autoContrast: true,
  luminanceThreshold: 0.35,
  black: "#13161E",
  fontFamily: "var(--font-plex), 'Segoe UI', sans-serif",
  fontFamilyMonospace: "var(--font-plex-mono), ui-monospace, monospace",
  headings: { fontFamily: "var(--font-plex), 'Segoe UI', sans-serif", fontWeight: "700" },
  radius: { xs: "3px", sm: "5px", md: "5px", lg: "8px", xl: "999px" },
  defaultRadius: "sm",
});

export function MantineShell({ children }: { children: React.ReactNode }) {
  return (
    <DirectionProvider initialDirection="rtl" detectDirection={false}>
      <MantineProvider theme={theme} forceColorScheme="light">
        {children}
      </MantineProvider>
    </DirectionProvider>
  );
}
