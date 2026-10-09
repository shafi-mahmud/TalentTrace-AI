const API_BASE = (import.meta.env?.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
export interface RecruiterAccount {id: string; email: string;}

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("X-TalentTrace-Request", "1");
  const response = await fetch(input, {...init, credentials: "include", headers});
  if (response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("talenttrace-session-expired"));
  return response;
}

export async function account(): Promise<RecruiterAccount | null> {
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {credentials: "include"});
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Sign-in service is unavailable. Check database readiness.");
  return validateAccount(await response.json());
}

function validateAccount(value: unknown): RecruiterAccount {
  if (typeof value !== "object" || value === null || !("id" in value) || !("email" in value)
    || typeof value.id !== "string" || typeof value.email !== "string") throw new Error("Invalid sign-in response.");
  return {id: value.id, email: value.email};
}

export async function signIn(email: string, password: string) {
  const response = await authenticatedFetch(`${API_BASE}/api/v1/auth/login`, {method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify({email, password})});
  if (!response.ok) throw new Error(response.status === 429 ? "Too many attempts. Wait five minutes." : "Sign-in failed. Check your details and service readiness.");
  return validateAccount(await response.json());
}

export async function signOut() {
  const response = await authenticatedFetch(`${API_BASE}/api/v1/auth/logout`, {method: "POST"});
  if (!response.ok) throw new Error("Sign-out was not confirmed. Please try again.");
}
