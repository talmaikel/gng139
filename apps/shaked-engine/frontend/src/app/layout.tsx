import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "שקדן · מועמדים",
  description: "איתור מגרשים להתחדשות עירונית במסלול חלופת שקד, לחברות יזמיות",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
