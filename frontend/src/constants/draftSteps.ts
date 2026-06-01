import type { DraftStep, Team } from "../types/draft";

export const BANS_PER_TEAM = 3;
export const PICKS_PER_TEAM = 3;

/** Snake pick order after bans (blue picks first variant). */
const PICKS_BLUE_FIRST: Omit<DraftStep, "index">[] = [
  { action: "pick", team: "blue", teamSlot: 0, pickNumber: 2 },
  { action: "pick", team: "red", teamSlot: 0, pickNumber: 3 },
  { action: "pick", team: "red", teamSlot: 1, pickNumber: 4 },
  { action: "pick", team: "blue", teamSlot: 1, pickNumber: 5 },
  { action: "pick", team: "blue", teamSlot: 2, pickNumber: 6 },
  { action: "pick", team: "red", teamSlot: 2, pickNumber: 6 },
];

/** Snake pick order after bans (red picks first variant). */
const PICKS_RED_FIRST: Omit<DraftStep, "index">[] = [
  { action: "pick", team: "red", teamSlot: 0, pickNumber: 2 },
  { action: "pick", team: "blue", teamSlot: 0, pickNumber: 3 },
  { action: "pick", team: "blue", teamSlot: 1, pickNumber: 4 },
  { action: "pick", team: "red", teamSlot: 1, pickNumber: 5 },
  { action: "pick", team: "red", teamSlot: 2, pickNumber: 6 },
  { action: "pick", team: "blue", teamSlot: 2, pickNumber: 6 },
];

export function buildPickSteps(firstPickTeam: Team): DraftStep[] {
  const template = firstPickTeam === "blue" ? PICKS_BLUE_FIRST : PICKS_RED_FIRST;
  return template.map((step, index) => ({ ...step, index }));
}

export function teamLabel(team: Team): string {
  return team === "blue" ? "Blue" : "Red";
}

export function formatWinRate(value: number): string {
  return `${Math.round(value * 100)}%`;
}
