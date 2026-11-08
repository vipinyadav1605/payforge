// Tiny API client. All calls go to /api/* which Vite proxies to the PayForge API.
const KEY = "payforge_api_key";

export const getKey = () => localStorage.getItem(KEY);
export const setKey = (k) => localStorage.setItem(KEY, k);
export const clearKey = () => localStorage.removeItem(KEY);

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Returns { data, headers, status }. Throws ApiError on non-2xx using the API's error envelope. */
export async function api(path, { method = "GET", body, idempotencyKey, key, adminToken } = {}) {
  const headers = { "Content-Type": "application/json" };
  const apiKey = key ?? getKey();
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  if (adminToken) headers["X-Admin-Token"] = adminToken;
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const e = data?.error || {};
    throw new ApiError(res.status, e.code || "error", e.message || res.statusText, e.details);
  }
  return { data, status: res.status, headers: res.headers };
}

export const newIdempotencyKey = () => crypto.randomUUID();

/** Amounts are integers in the smallest unit (cents/paise). */
export function money(amount, currency) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: (currency || "usd").toUpperCase(),
  }).format((amount || 0) / 100);
}

export const when = (epoch) => new Date(epoch * 1000).toLocaleString();
