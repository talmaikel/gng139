import type { ReactNode } from "react";

/** המסגרת של מסכי הכניסה, ההרשמה והשחזור — אותו מראה בכולם.
 *  הלוגו מגיע מ-`.auth-card::before` ב-globals.css. */
export default function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="page">
      <div className="card auth-card">
        <p className="eyebrow">חלופת שקד · הרצליה</p>
        <h1>{title}</h1>
        {children}
      </div>
    </main>
  );
}

export const authInputLtr = { textAlign: "start" as const };
export const authError = { color: "var(--bad-fg)", fontSize: ".88rem" };
export const authOk = { color: "var(--ok-fg)", fontSize: ".92rem" };
export const authFooter = { marginTop: "1.2rem", fontSize: ".88rem" };
