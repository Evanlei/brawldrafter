import type { Recommendation, RecommendationPayload } from "../types/draft";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

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
  const response = await fetch(`${API_BASE}/api/v1/recommendations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }

  const data = (await response.json()) as ApiResponse;
  return data.recommendations.map(mapRecommendation);
}
