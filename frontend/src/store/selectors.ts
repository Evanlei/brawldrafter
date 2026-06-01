import { BANS_PER_TEAM } from "../constants/draftSteps";
import type {
  BrawlerOption,
  DraftSession,
  DraftStep,
  RecommendationPayload,
} from "../types/draft";

export function getCurrentPickStep(session: DraftSession): DraftStep | null {
  if (session.subPhase !== "picks") {
    return null;
  }
  return session.pickSteps[session.currentPickStepIndex] ?? null;
}

export function isDraftComplete(session: DraftSession): boolean {
  return (
    session.subPhase === "picks" &&
    session.currentPickStepIndex >= session.pickSteps.length
  );
}

export function isBanPhaseComplete(session: DraftSession): boolean {
  const filled = (slots: Array<number | null>) =>
    slots.length === BANS_PER_TEAM && slots.every((id) => id !== null);
  return filled(session.blueBans) && filled(session.redBans);
}

export function getTakenBrawlerIds(session: DraftSession): Set<number> {
  const taken = new Set<number>([
    ...session.bluePicks,
    ...session.redPicks,
  ]);

  if (session.subPhase === "picks") {
    for (const id of session.blueBans) {
      if (id !== null) taken.add(id);
    }
    for (const id of session.redBans) {
      if (id !== null) taken.add(id);
    }
  }

  return taken;
}

export function getAvailableBrawlers(
  brawlers: BrawlerOption[],
  session: DraftSession,
): BrawlerOption[] {
  const taken = getTakenBrawlerIds(session);
  return brawlers.filter((b) => !taken.has(b.brawlerId));
}

export function shouldFetchRecommendations(session: DraftSession): boolean {
  if (session.subPhase !== "picks" || isDraftComplete(session)) {
    return false;
  }
  const step = getCurrentPickStep(session);
  return step?.team === "blue" && step.action === "pick";
}

export function toRecommendationPayload(session: DraftSession): RecommendationPayload {
  const step = getCurrentPickStep(session);
  const pickNumber = step?.pickNumber ?? 1;
  const compactBans = (slots: Array<number | null>) =>
    slots.filter((id): id is number => id !== null);

  return {
    map_id: session.mapId,
    mode_id: session.modeId,
    first_pick_team: session.firstPickTeam,
    blue_bans: compactBans(session.blueBans),
    red_bans: compactBans(session.redBans),
    blue_picks: [...session.bluePicks],
    red_picks: [...session.redPicks],
    current_pick_number: session.subPhase === "bans" ? 1 : pickNumber,
  };
}

export function getBrawlerName(
  brawlers: BrawlerOption[],
  brawlerId: number,
): string {
  return brawlers.find((b) => b.brawlerId === brawlerId)?.name ?? `Brawler ${brawlerId}`;
}
