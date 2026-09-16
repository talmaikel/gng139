"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import AuthCard, { authError, authFooter, authOk } from "@/components/AuthCard";
import { ApiError, verifyEmail } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [message, setMessage] = useState("");
  const started = useRef(false);

  useEffect(() => {
    // פעם אחת בלבד: טוקן שנשלח פעמיים מחזיר ״כבר מאומת״ בפעם השנייה.
    if (started.current) return;
    started.current = true;
    if (!token) {
      setState("error");
      setMessage("חסר קישור אימות.");
      return;
    }
    verifyEmail(token)
      .then(() => setState("ok"))
      .catch((e) => {
        const detail = e instanceof ApiError ? e.detail : "האימות נכשל.";
        // מי שלחץ פעמיים על הקישור כבר מאומת — זו לא שגיאה בשבילו.
        if (detail.includes("כבר מאומתת")) setState("ok");
        else {
          setState("error");
          setMessage(detail);
        }
      });
  }, [token]);

  if (state === "working") return <p>מאמת…</p>;
  if (state === "ok") return <p style={authOk}>כתובת המייל אומתה. תודה!</p>;
  return (
    <p style={authError}>
      {message} אפשר לבקש קישור חדש מהמסך הראשי אחרי הכניסה.
    </p>
  );
}

export default function VerifyPage() {
  return (
    <AuthCard title="אימות כתובת מייל">
      <Suspense fallback={<p>טוען…</p>}>
        <Verify />
      </Suspense>
      <p style={authFooter}>
        <Link href="/dashboard">למסך הראשי</Link>
      </p>
    </AuthCard>
  );
}
