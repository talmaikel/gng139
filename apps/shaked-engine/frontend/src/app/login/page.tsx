"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, login, setToken } from "@/lib/api";

function isLocalBrowser(): boolean {
  if (typeof window === "undefined") return false;
  return ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [autoLoggingIn, setAutoLoggingIn] = useState(true);

  useEffect(() => {
    if (!isLocalBrowser()) {
      setAutoLoggingIn(false);
      return;
    }

    let cancelled = false;

    async function autoLogin() {
      try {
        const response = await fetch("/dev-auto-login", {
          method: "POST",
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Auto-login unavailable");

        const { access_token } = await response.json();
        if (cancelled) return;
        setToken(access_token);
        router.replace("/dashboard");
      } catch {
        if (!cancelled) setAutoLoggingIn(false);
      }
    }

    void autoLogin();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { access_token } = await login(email, password);
      setToken(access_token);
      router.push("/dashboard");
    } catch (e) {
      // ‏429 אינו ״סיסמה שגויה״ — מי שנחסם צריך לדעת שעליו לחכות.
      setError(e instanceof ApiError && e.status === 429 ? e.detail : "כתובת או סיסמה שגויות.");
    } finally {
      setSubmitting(false);
    }
  }

  if (autoLoggingIn) {
    return (
      <main className="page">
        <div className="card" style={{ maxWidth: 380, margin: "3.5rem auto" }}>
          <p style={{ margin: 0, color: "#6b655c", fontSize: ".82rem", letterSpacing: ".08em" }}>
            חלופת שקד · הרצליה
          </p>
          <h1 style={{ margin: ".15rem 0 1.2rem" }}>מתחבר…</h1>
        </div>
      </main>
    );
  }

  return (
    <main className="page">
      <div className="card" style={{ maxWidth: 380, margin: "3.5rem auto" }}>
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
        <p style={{ marginTop: "1.2rem", fontSize: ".88rem" }}>
          לקוח חדש? <Link href="/signup">הרשמה</Link>
          {" · "}
          <Link href="/forgot-password">שכחתי סיסמה</Link>
        </p>
      </div>
    </main>
  );
}
