import "@mantine/core/styles.css";
import "@mantine/carousel/styles.css";
import { fontRootCss } from "@/components/brand/fonts";
import { MantineShell } from "@/components/brand/MantineShell";

// Trial route for the Mantine design language.
export default function DesignLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <style>{fontRootCss}</style>
      <MantineShell>{children}</MantineShell>
    </>
  );
}
