import { create } from "zustand";

import { postRecommendations } from "../api/recommendations";
import { BANS_PER_TEAM, buildPickSteps } from "../constants/draftSteps";
import {
  getAvailableBrawlers,
  isBanPhaseComplete,
  isDraftComplete,
  shouldFetchRecommendations,
  toRecommendationPayload,
} from "../store/selectors";
import type {
  BanSlotTarget,
  BrawlerOption,
  Catalog,
  DraftSession,
  GameModeOption,
  LobbyState,
  MapOption,
  RecommendationsState,
  Team,
  ViewPhase,
} from "../types/draft";
import catalogData from "../data/catalog.json";

const catalog = catalogData as Catalog;

const initialLobby: LobbyState = {
  selectedModeId: null,
  selectedMapId: null,
  firstPickTeam: "blue",
};

function emptyBanSlots(): Array<number | null> {
  return [null, null, null];
}

const initialRecommendations: RecommendationsState = {
  items: [],
  status: "idle",
  error: null,
  requestKey: null,
};

let fetchTimer: ReturnType<typeof setTimeout> | null = null;
let fetchGeneration = 0;

interface DraftStore {
  phase: ViewPhase;
  lobby: LobbyState;
  session: DraftSession | null;
  modes: GameModeOption[];
  maps: MapOption[];
  brawlers: BrawlerOption[];
  targetedBanSlot: BanSlotTarget | null;
  recommendations: RecommendationsState;

  setMode: (modeId: number | null) => void;
  setMap: (mapId: number | null) => void;
  setFirstPickTeam: (team: Team) => void;
  startDraft: () => boolean;
  setTargetedBanSlot: (target: BanSlotTarget | null) => void;
  assignBan: (team: Team, slotIndex: number, brawlerId: number) => void;
  clearBanSlot: (team: Team, slotIndex: number) => void;
  continueToPicks: () => void;
  selectBrawlerForPick: (brawlerId: number) => void;
  undoLastPick: () => void;
  resetDraft: () => void;
  fetchRecommendations: () => void;
  loadCatalog: (catalog: Catalog) => void;
}

function buildSession(
  lobby: LobbyState,
  modes: GameModeOption[],
  maps: MapOption[],
): DraftSession | null {
  const { selectedModeId, selectedMapId, firstPickTeam } = lobby;
  if (selectedModeId == null || selectedMapId == null) {
    return null;
  }

  const mode = modes.find((m) => m.modeId === selectedModeId);
  const map = maps.find((m) => m.mapId === selectedMapId);
  if (!mode || !map) {
    return null;
  }

  return {
    modeId: selectedModeId,
    mapId: selectedMapId,
    mapName: map.name,
    modeLabel: mode.label,
    firstPickTeam,
    subPhase: "bans",
    blueBans: emptyBanSlots(),
    redBans: emptyBanSlots(),
    bluePicks: [],
    redPicks: [],
    currentPickStepIndex: 0,
    pickSteps: buildPickSteps(firstPickTeam),
  };
}

function scheduleRecommendationsFetch(fetchFn: () => void) {
  if (fetchTimer) {
    clearTimeout(fetchTimer);
  }
  fetchTimer = setTimeout(fetchFn, 300);
}

export const useDraftStore = create<DraftStore>((set, get) => ({
  phase: "lobby",
  lobby: initialLobby,
  session: null,
  modes: catalog.modes,
  maps: catalog.maps,
  brawlers: catalog.brawlers,
  targetedBanSlot: null,
  recommendations: initialRecommendations,

  setMode: (modeId) => {
    set((state) => ({
      lobby: {
        ...state.lobby,
        selectedModeId: modeId,
        selectedMapId: null,
      },
    }));
  },

  setMap: (mapId) => {
    set((state) => ({
      lobby: { ...state.lobby, selectedMapId: mapId },
    }));
  },

  setFirstPickTeam: (team) => {
    set((state) => ({
      lobby: { ...state.lobby, firstPickTeam: team },
    }));
  },

  startDraft: () => {
    const { lobby, modes, maps } = get();
    const session = buildSession(lobby, modes, maps);
    if (!session) {
      return false;
    }
    set({
      phase: "draft",
      session,
      targetedBanSlot: { team: "blue", slotIndex: 0 },
      recommendations: initialRecommendations,
    });
    return true;
  },

  setTargetedBanSlot: (target) => set({ targetedBanSlot: target }),

  assignBan: (team, slotIndex, brawlerId) => {
    const { session } = get();
    if (!session || session.subPhase !== "bans") {
      return;
    }
    if (slotIndex < 0 || slotIndex >= BANS_PER_TEAM) {
      return;
    }

    const key = team === "blue" ? "blueBans" : "redBans";
    const slots = [...session[key]];
    while (slots.length < BANS_PER_TEAM) {
      slots.push(null);
    }
    slots[slotIndex] = brawlerId;

    set({
      session: {
        ...session,
        [key]: slots.slice(0, BANS_PER_TEAM),
      },
    });
  },

  clearBanSlot: (team, slotIndex) => {
    const { session } = get();
    if (!session || session.subPhase !== "bans") {
      return;
    }
    if (slotIndex < 0 || slotIndex >= BANS_PER_TEAM) {
      return;
    }

    const key = team === "blue" ? "blueBans" : "redBans";
    const slots = [...session[key]];
    while (slots.length < BANS_PER_TEAM) {
      slots.push(null);
    }
    slots[slotIndex] = null;

    set({ session: { ...session, [key]: slots } });
  },

  continueToPicks: () => {
    const { session } = get();
    if (!session || !isBanPhaseComplete(session)) {
      return;
    }

    set({
      session: { ...session, subPhase: "picks", currentPickStepIndex: 0 },
      targetedBanSlot: null,
      recommendations: initialRecommendations,
    });
    scheduleRecommendationsFetch(() => get().fetchRecommendations());
  },

  selectBrawlerForPick: (brawlerId) => {
    const { session, brawlers } = get();
    if (!session || session.subPhase !== "picks" || isDraftComplete(session)) {
      return;
    }

    const step = session.pickSteps[session.currentPickStepIndex];
    if (!step) {
      return;
    }

    const available = getAvailableBrawlers(brawlers, session);
    if (!available.some((b) => b.brawlerId === brawlerId)) {
      return;
    }

    const pickKey = step.team === "blue" ? "bluePicks" : "redPicks";
    const updated: DraftSession = {
      ...session,
      [pickKey]: [...session[pickKey], brawlerId],
      currentPickStepIndex: session.currentPickStepIndex + 1,
    };

    set({ session: updated });
    scheduleRecommendationsFetch(() => get().fetchRecommendations());
  },

  undoLastPick: () => {
    const { session } = get();
    if (!session || session.subPhase !== "picks" || session.currentPickStepIndex === 0) {
      return;
    }

    const prevIndex = session.currentPickStepIndex - 1;
    const prevStep = session.pickSteps[prevIndex];
    const pickKey = prevStep.team === "blue" ? "bluePicks" : "redPicks";
    const picks = [...session[pickKey]];
    picks.pop();

    set({
      session: {
        ...session,
        [pickKey]: picks,
        currentPickStepIndex: prevIndex,
      },
      recommendations: initialRecommendations,
    });
    scheduleRecommendationsFetch(() => get().fetchRecommendations());
  },

  resetDraft: () => {
    if (fetchTimer) {
      clearTimeout(fetchTimer);
      fetchTimer = null;
    }
    fetchGeneration += 1;
    set({
      phase: "lobby",
      session: null,
      targetedBanSlot: null,
      recommendations: initialRecommendations,
    });
  },

  loadCatalog: (catalog) => {
    set({
      modes: catalog.modes,
      maps: catalog.maps,
      brawlers: catalog.brawlers,
    });
  },

  fetchRecommendations: () => {
    const { session, recommendations } = get();
    if (!session || !shouldFetchRecommendations(session)) {
      set({
        recommendations: {
          ...initialRecommendations,
          status: "idle",
        },
      });
      return;
    }

    const payload = toRecommendationPayload(session);
    const requestKey = JSON.stringify(payload);

    if (
      recommendations.status === "loading" &&
      recommendations.requestKey === requestKey
    ) {
      return;
    }

    const generation = ++fetchGeneration;
    set({
      recommendations: {
        items: [],
        status: "loading",
        error: null,
        requestKey,
      },
    });

    postRecommendations(payload)
      .then((items) => {
        if (generation !== fetchGeneration) {
          return;
        }
        set({
          recommendations: {
            items,
            status: "success",
            error: null,
            requestKey,
          },
        });
      })
      .catch((error: unknown) => {
        if (generation !== fetchGeneration) {
          return;
        }
        const message = error instanceof Error ? error.message : "Failed to load recommendations";
        set({
          recommendations: {
            items: [],
            status: "error",
            error: message,
            requestKey,
          },
        });
      });
  },
}));
