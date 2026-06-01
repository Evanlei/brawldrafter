import type { Recommendation, RecommendationPayload } from "../types/draft";
import { apiUrl, isApiConfigured } from "./client";

interface ApiRecommendation {
  brawler_id: number;
  name: string;
  confidence: number;
  reason: string;
}

interface ApiResponse {
  recommendations: ApiRecommendation[];
}

function mapRecommendation(item: ApiRecommendation): Recommendation {
  return {
    brawlerId: item.brawler_id,
    name: item.name,
    confidence: item.confidence,
    reason: item.reason,
  };
}

export async function postRecommendations(
  body: RecommendationPayload,
): Promise<Recommendation[]> {
  const response = await fetch(apiUrl("/api/v1/recommendations"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

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
