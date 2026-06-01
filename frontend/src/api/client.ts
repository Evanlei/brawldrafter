/** Backend origin. Empty → same-origin `/api` (Vercel rewrite or Vite dev proxy). */
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

function resolveApiBase(): string {
  const configured = normalizeApiBase(import.meta.env.VITE_API_BASE);
  if (!configured || typeof window === "undefined") {
    return configured;
  }
  try {
    const apiOrigin = new URL(configured).origin;
    if (apiOrigin !== window.location.origin) {
      // Cross-origin (e.g. Vercel UI + Railway VITE_API_BASE) → CORS "Load failed" in Safari
      return "";
    }
  } catch {
    return configured;
  }
  return configured;
}

export const API_BASE = resolveApiBase();

export function isApiConfigured(): boolean {
  return API_BASE.length > 0;
}

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}
