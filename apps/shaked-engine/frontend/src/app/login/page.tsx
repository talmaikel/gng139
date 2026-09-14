"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { login, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { access_token } = await login(email, password);
      setToken(access_token);
      router.push("/dashboard");
    } catch {
      setError("כתובת או סיסמה שגויות.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <div className="card" style={{ maxWidth: 380, margin: "3.5rem auto" }}>
        {/* מסך ההתחברות הוא הדבר הראשון שכל אחד רואה — ועד כה הוא היה
            באנגלית בעוד כל השאר עברית. */}
        <p style={{ margin: 0, color: "#6b655c", fontSize: ".82rem", letterSpacing: ".08em" }}>
          חלופת שקד · הרצליה
        </p>
        <h1 style={{ margin: ".15rem 0 1.2rem" }}>כניסה</h1>
        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label htmlFor="email">דואר אלקטרוני</label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              dir="ltr"
              style={{ textAlign: "start" }}
            />
          </div>
          <div className="form-field">
            <label htmlFor="password">סיסמה</label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              dir="ltr"
              style={{ textAlign: "start" }}
            />
          </div>
          {error && <p style={{ color: "#a8321e", fontSize: ".88rem" }}>{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? "מתחבר…" : "כניסה"}
          </button>
        </form>
      </div>
    </main>
  );
}
