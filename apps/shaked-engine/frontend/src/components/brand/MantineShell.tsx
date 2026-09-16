"use client";

import {
  Alert, Badge, Button, createTheme, DirectionProvider, MantineProvider, NumberInput, Paper,
  Select, Table, TextInput, Textarea, type CSSVariablesResolver, type MantineColorsTuple,
} from "@mantine/core";

// Almond from the shakdan logo; index 5 is the brand #E8894A.
const almond: MantineColorsTuple = [
  "#FFF4EC", "#FDE6D6", "#F8C9A8", "#F3AB78", "#EE9458",
  "#E8894A", "#D9783A", "#C96F33", "#A85A28", "#86461E",
];
// Semantic only: green says "passed", red says "failed". Never decoration.
const moss: MantineColorsTuple = [
  "#EEF7F1", "#DCEFE3", "#BFE0CC", "#9BCDB0", "#74B592",
  "#4F9A73", "#367E5A", "#1F5A3C", "#174630", "#103324",
];
const brick: MantineColorsTuple = [
  "#FCF3F1", "#F5E4E0", "#ECC6BD", "#E0A497", "#D28371",
  "#C2634E", "#B04F3B", "#A2402E", "#833224", "#66271C",
];

const theme = createTheme({
  colors: { almond, moss, brick },
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
  components: {
    Badge: Badge.extend({ defaultProps: { variant: "light", radius: "sm", tt: "none", fw: 700 } }),
    Paper: Paper.extend({ defaultProps: { withBorder: true, radius: "sm" } }),
    Alert: Alert.extend({ defaultProps: { variant: "light", radius: "sm" } }),
    Table: Table.extend({ defaultProps: { verticalSpacing: "sm" } }),
    Button: Button.extend({ defaultProps: { radius: "sm" } }),
    TextInput: TextInput.extend({ defaultProps: { radius: "sm" } }),
    Textarea: Textarea.extend({ defaultProps: { radius: "sm" } }),
    NumberInput: NumberInput.extend({ defaultProps: { radius: "sm" } }),
    Select: Select.extend({ defaultProps: { radius: "sm" } }),
  },
});

// Pin the "light" variants to the exact status tokens in globals.css, so a
// Badge and a .pill next to each other are the same colour.
const resolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    "--mantine-color-text": "#13161E",
    "--mantine-color-dimmed": "#5B6068",
    "--mantine-color-default-border": "#DDE0E6",
    "--mantine-color-moss-light": "#DCEFE3",
    "--mantine-color-moss-light-color": "#1F5A3C",
    "--mantine-color-moss-light-hover": "#BFE0CC",
    "--mantine-color-brick-light": "#F5E4E0",
    "--mantine-color-brick-light-color": "#A2402E",
    "--mantine-color-brick-light-hover": "#ECC6BD",
    "--mantine-color-almond-light": "#FDEEE3",
    "--mantine-color-almond-light-color": "#C96F33",
    "--mantine-color-almond-light-hover": "#F8C9A8",
    "--mantine-color-gray-light": "#EBEDF1",
    "--mantine-color-gray-light-color": "#5B6068",
  },
  dark: {},
});

export function MantineShell({ children }: { children: React.ReactNode }) {
  return (
    <DirectionProvider initialDirection="rtl" detectDirection={false}>
      <MantineProvider theme={theme} forceColorScheme="light" cssVariablesResolver={resolver}>
        {children}
      </MantineProvider>
    </DirectionProvider>
  );
}
