import type { ReactNode } from "react";

/** המסגרת של מסכי הכניסה, ההרשמה והשחזור — אותו מראה בכולם. */
export default function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="page">
      <div className="card" style={{ maxWidth: 380, margin: "3.5rem auto" }}>
        <p style={{ margin: 0, color: "#6b655c", fontSize: ".82rem", letterSpacing: ".08em" }}>
          חלופת שקד · הרצליה
        </p>
        <h1 style={{ margin: ".15rem 0 1.2rem" }}>{title}</h1>
        {children}
      </div>
    </main>
  );
}

export const authInputLtr = { textAlign: "start" as const };
export const authError = { color: "#a8321e", fontSize: ".88rem" };
export const authOk = { color: "#1f5f55", fontSize: ".92rem" };
export const authFooter = { marginTop: "1.2rem", fontSize: ".88rem" };
