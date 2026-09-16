"use client";

import Link from "next/link";
import { useState } from "react";
import AuthCard, { authError, authFooter, authInputLtr, authOk } from "@/components/AuthCard";
import { ApiError, forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "הבקשה נכשלה. אפשר לנסות שוב.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard title="שכחתי סיסמה">
      {sent ? (
        // אותה תשובה למייל רשום ולא רשום — השרת אינו מגלה מי לקוח.
        <p style={authOk}>
          אם הכתובת רשומה אצלנו, נשלח אליה קישור לאיפוס הסיסמה. הקישור תקף לשעה.
        </p>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label htmlFor="email">דואר אלקטרוני</label>
            <input id="email" type="email" required autoComplete="email" dir="ltr"
                   style={authInputLtr} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          {error && <p style={authError}>{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? "שולח…" : "שליחת קישור לאיפוס"}
          </button>
        </form>
      )}
      <p style={authFooter}>
        <Link href="/login">חזרה לכניסה</Link>
      </p>
    </AuthCard>
  );
}
