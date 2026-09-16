"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import AuthCard, { authError, authFooter, authInputLtr, authOk } from "@/components/AuthCard";
import { ApiError, resetPassword } from "@/lib/api";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("שתי הסיסמאות אינן זהות.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "האיפוס נכשל. אפשר לנסות שוב.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <p style={authError}>
        חסר קישור איפוס. <Link href="/forgot-password">לבקש קישור חדש</Link>
      </p>
    );
  }
  if (done) {
    return (
      <p style={authOk}>
        הסיסמה עודכנה. <Link href="/login">לכניסה</Link>
      </p>
    );
  }
  return (
    <form onSubmit={handleSubmit}>
      <div className="form-field">
        <label htmlFor="password">סיסמה חדשה (8 תווים לפחות)</label>
        <input id="password" type="password" required minLength={8} autoComplete="new-password"
               dir="ltr" style={authInputLtr} value={password} onChange={(e) => setPassword(e.target.value)} />
      </div>
      <div className="form-field">
        <label htmlFor="confirm">שוב את הסיסמה</label>
        <input id="confirm" type="password" required minLength={8} autoComplete="new-password"
               dir="ltr" style={authInputLtr} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </div>
      {error && (
        <p style={authError}>
          {error} {error.includes("קישור") && <Link href="/forgot-password">לבקש קישור חדש</Link>}
        </p>
      )}
      <button type="submit" disabled={submitting}>
        {submitting ? "מעדכן…" : "עדכון סיסמה"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthCard title="איפוס סיסמה">
      {/* ‏useSearchParams דורש Suspense ב-Next 15, אחרת ה-build נכשל */}
      <Suspense fallback={<p>טוען…</p>}>
        <ResetForm />
      </Suspense>
      <p style={authFooter}>
        <Link href="/login">חזרה לכניסה</Link>
      </p>
    </AuthCard>
  );
}
