"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, setToken, signup } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { access_token } = await signup({
        company_name: companyName,
        full_name: fullName,
        email,
        password,
      });
      setToken(access_token);
      router.push("/dashboard");
    } catch (e) {
      // ‏422 של ולידציה (למשל מייל לא תקין) מגיע בלי משפט — ה-FALLBACK
      // אומר ״הבקשה אינה תקינה״, וזה מספיק כדי שהגולש יבדוק את השדות.
      setError(e instanceof ApiError ? e.detail : "ההרשמה נכשלה. אפשר לנסות שוב.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <div className="card" style={{ maxWidth: 380, margin: "3.5rem auto" }}>
        <p style={{ margin: 0, color: "#6b655c", fontSize: ".82rem", letterSpacing: ".08em" }}>
          חלופת שקד · הרצליה
        </p>
        <h1 style={{ margin: ".15rem 0 1.2rem" }}>הרשמה</h1>
        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label htmlFor="company">שם החברה</label>
            <input
              id="company"
              required
              minLength={2}
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="full-name">שם מלא</label>
            <input
              id="full-name"
              required
              minLength={2}
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="email">דואר אלקטרוני</label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              dir="ltr"
              style={{ textAlign: "start" }}
            />
          </div>
          <div className="form-field">
            <label htmlFor="password">סיסמה (8 תווים לפחות)</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              dir="ltr"
              style={{ textAlign: "start" }}
            />
          </div>
          {error && <p style={{ color: "#a8321e", fontSize: ".88rem" }}>{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? "נרשם…" : "הרשמה"}
          </button>
        </form>
        <p style={{ marginTop: "1.2rem", fontSize: ".88rem" }}>
          כבר יש חשבון? <Link href="/login">כניסה</Link>
        </p>
      </div>
    </main>
  );
}
