import type { Recommendation, RecommendationPayload } from "../types/draft";
import { apiUrl, isApiConfigured } from "./client";

interface ApiRecommendation {
  brawler_id: number;
  name: string;
  map_win_rate: number;
  pick_score: number;
  reason: string;
}

interface ApiResponse {
  recommendations: ApiRecommendation[];
}

function mapRecommendation(item: ApiRecommendation): Recommendation {
  return {
    brawlerId: item.brawler_id,
    name: item.name,
    mapWinRate: item.map_win_rate,
    pickScore: item.pick_score,
    reason: item.reason,
  };
}

export async function postRecommendations(
  body: RecommendationPayload,
): Promise<Recommendation[]> {
  const url = apiUrl("/api/v1/recommendations");
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Network error";
    if (/load failed|failed to fetch/i.test(msg)) {
      throw new Error(
        "Cannot reach the API (network or CORS). Redeploy the frontend or remove VITE_API_BASE so requests use the /api proxy.",
      );
    }
    throw err instanceof Error ? err : new Error(msg);
  }

  if (!response.ok) {
    const detail = await response.text();
    if (response.status === 405 && !isApiConfigured()) {
      throw new Error(
        "Could not reach the API. Redeploy the frontend after pulling latest vercel.json, or set VITE_API_BASE to your Railway URL.",
      );
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }

  const data = (await response.json()) as ApiResponse;
  return data.recommendations.map(mapRecommendation);
}
