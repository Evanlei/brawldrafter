/** Backend origin in production. Empty → same-origin `/api` (Vercel rewrite or Vite dev proxy). */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export function isApiConfigured(): boolean {
  return API_BASE.length > 0;
}

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}
