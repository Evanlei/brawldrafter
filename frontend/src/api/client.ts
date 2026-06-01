/** Backend origin in production. Empty → same-origin `/api` (Vercel rewrite or Vite dev proxy). */
function normalizeApiBase(raw: string | undefined): string {
  const trimmed = (raw ?? "").trim().replace(/\/$/, "");
  if (!trimmed) {
    return "";
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  // Vercel env without scheme is treated as a relative path → 405 on POST
  return `https://${trimmed}`;
}

export const API_BASE = normalizeApiBase(import.meta.env.VITE_API_BASE);

export function isApiConfigured(): boolean {
  return API_BASE.length > 0;
}

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}
