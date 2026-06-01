import type { BrawlerOption, Catalog, GameModeOption, MapOption } from "../types/draft";

type ModeDto = { modeId: number; name: string; label: string };
type MapDto = { mapId: number; name: string; modeId: number };
type BrawlerDto = { brawlerId: number; name: string };

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Catalog request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function fetchCatalog(): Promise<Catalog> {
  const [modes, maps, brawlers] = await Promise.all([
    fetchJson<ModeDto[]>("/api/v1/modes"),
    fetchJson<MapDto[]>("/api/v1/maps"),
    fetchJson<BrawlerDto[]>("/api/v1/brawlers"),
  ]);

  return {
    modes: modes as GameModeOption[],
    maps: maps as MapOption[],
    brawlers: brawlers as BrawlerOption[],
  };
}
