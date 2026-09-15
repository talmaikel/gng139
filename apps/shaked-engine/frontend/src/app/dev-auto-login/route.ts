import { NextRequest, NextResponse } from "next/server";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

export async function POST(request: NextRequest) {
  if (process.env.NODE_ENV === "production" || !isLocalHost(request.nextUrl.hostname)) {
    return NextResponse.json({ detail: "Not available" }, { status: 404 });
  }

  // Local-development defaults match the dev account created by RUN_LOCAL.md.
  // Environment variables can still override them without exposing either
  // value to browser JavaScript.
  const email = process.env.DEV_AUTO_LOGIN_EMAIL ?? "dev@shaked.example.com";
  const password = process.env.DEV_AUTO_LOGIN_PASSWORD ?? "devpass12345";

  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_ORIGIN}/api/v1/auth/jwt/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });

  if (!response.ok) {
    return NextResponse.json({ detail: "Dev auto-login failed" }, { status: 401 });
  }

  const token = await response.json();
  return NextResponse.json(token, { headers: { "Cache-Control": "no-store" } });
}
