const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("shaked_token");
}

export function setToken(token: string): void {
  window.localStorage.setItem("shaked_token", token);
}

export function clearToken(): void {
  window.localStorage.removeItem("shaked_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API request failed (${response.status}): ${body}`);
  }
  return response.json() as Promise<T>;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/jwt/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new Error("Login failed");
  }
  return response.json() as Promise<LoginResponse>;
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: number[][][][]; // GeoJSON order: [lng, lat] per position
}

export interface Candidate {
  id: string;
  address: string;
  block: string | null;
  parcel: string | null;
  xplan_code: string | null;
  area_sqm: number | null;
  verification_level: string;
  category: string | null;
  geometry: MultiPolygonGeometry | null;
  centroid: { lat: number; lng: number } | null;
}

export function getCandidates(cityCode: string): Promise<Candidate[]> {
  return request<Candidate[]>(`/api/v1/candidates/${cityCode}`);
}
