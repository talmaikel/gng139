import { NextRequest, NextResponse } from "next/server";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const LOOPBACK_ADDRESSES = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

// Added only when a request passed through Cloudflare — e.g. the demo
// `cloudflared` tunnel. A browser on this machine never sends them.
const CLOUDFLARE_HEADERS = ["cf-connecting-ip", "cf-ray", "cf-visitor", "cdn-loop"];

function hostnameOf(hostHeader: string | null): string {
  if (!hostHeader) return "";
  // "[::1]:3000" -> "[::1]", "localhost:3000" -> "localhost"
  return hostHeader.startsWith("[")
    ? hostHeader.slice(0, hostHeader.indexOf("]") + 1)
    : hostHeader.split(":")[0];
}

/**
 * Is this request really from a browser on this machine?
 *
 * `request.nextUrl.hostname` cannot answer that: under `next dev` it is always
 * "localhost", whatever the request carried. On 15.09 a request with
 * `Host: abc.trycloudflare.com` — how a tunnel request arrives — was issued a
 * token, so with the demo tunnel open anyone holding the link was logged in
 * without a password.
 *
 * `next dev` itself adds X-Forwarded-For / -Host / -Port to every request
 * (for a local browser: `::ffff:127.0.0.1` and `localhost:3000`), so the mere
 * presence of those headers proves nothing. Three independent signals do:
 * the Host and X-Forwarded-Host must be local, every X-Forwarded-For hop
 * must be loopback, and no Cloudflare header may be present.
 */
function isDirectLocalRequest(request: NextRequest): boolean {
  const h = request.headers;
  if (!LOCAL_HOSTNAMES.has(hostnameOf(h.get("host")))) return false;
  const forwardedHost = h.get("x-forwarded-host");
  if (forwardedHost && !LOCAL_HOSTNAMES.has(hostnameOf(forwardedHost))) return false;
  const forwardedFor = h.get("x-forwarded-for");
  if (forwardedFor && !forwardedFor.split(",").every((ip) => LOOPBACK_ADDRESSES.has(ip.trim()))) {
    return false;
  }
  if (h.get("forwarded")) return false;
  return !CLOUDFLARE_HEADERS.some((name) => h.has(name));
}

export async function POST(request: NextRequest) {
  if (process.env.NODE_ENV === "production" || !isDirectLocalRequest(request)) {
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
