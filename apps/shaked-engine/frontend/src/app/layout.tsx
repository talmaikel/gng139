import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "שקדן · מועמדים",
  description: "Urban renewal opportunity screening under the Shaked Alternative",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
