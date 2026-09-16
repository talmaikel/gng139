import type { Metadata } from "next";

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: "התחברות | שקדן",
  description: "כניסה לחשבון שקדן: איתור מגרשים להתחדשות עירונית במסלול חלופת שקד.",
  alternates: { canonical: "https://gng139.online/login" },
  openGraph: { siteName: "שקדן", title: "התחברות | שקדן", url: "https://gng139.online/login", locale: "he_IL" },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
