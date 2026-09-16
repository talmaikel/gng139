import type { Metadata } from "next";

// The page is a client component, so its metadata lives here.
export const metadata: Metadata = {
  title: "הרשמה | שקדן",
  description: "פתיחת חשבון בשקדן: איתור מגרשים להתחדשות עירונית במסלול חלופת שקד, לחברות יזמיות.",
  alternates: { canonical: "https://gng139.online/signup" },
  openGraph: { siteName: "שקדן", title: "הרשמה | שקדן", url: "https://gng139.online/signup", locale: "he_IL" },
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
