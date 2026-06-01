export type Team = "blue" | "red";
export type DraftSubPhase = "bans" | "picks";
export type ViewPhase = "lobby" | "draft";

export interface GameModeOption {
  modeId: number;
  name: string;
  label: string;
}

export interface MapOption {
  mapId: number;
  modeId: number;
  name: string;
}

export interface BrawlerOption {
  brawlerId: number;
  name: string;
}

export interface DraftStep {
  index: number;
  action: "pick";
  team: Team;
  teamSlot: number;
  pickNumber: number;
}

export interface Recommendation {
  brawlerId: number;
  name: string;
  mapWinRate: number;
  pickScore: number;
  reason: string;
}

export interface LobbyState {
  selectedModeId: number | null;
  selectedMapId: number | null;
  firstPickTeam: Team;
}

export interface DraftSession {
  modeId: number;
  mapId: number;
  mapName: string;
  modeLabel: string;
  firstPickTeam: Team;
  subPhase: DraftSubPhase;
  blueBans: Array<number | null>;
  redBans: Array<number | null>;
  bluePicks: number[];
  redPicks: number[];
  currentPickStepIndex: number;
  pickSteps: DraftStep[];
}

export interface BanSlotTarget {
  team: Team;
  slotIndex: number;
}

export interface RecommendationsState {
  items: Recommendation[];
  status: "idle" | "loading" | "success" | "error";
  error: string | null;
  requestKey: string | null;
}

export interface Catalog {
  modes: GameModeOption[];
  maps: MapOption[];
  brawlers: BrawlerOption[];
}

export interface RecommendationPayload {
  map_id: number;
  mode_id: number;
  first_pick_team: Team;
  blue_bans: number[];
  red_bans: number[];
  blue_picks: number[];
  red_picks: number[];
  current_pick_number: number;
}
