import { BANS_PER_TEAM, teamLabel } from "../constants/draftSteps";
import { getBrawlerName } from "../store/selectors";
import { useDraftStore } from "../store/draftStore";
import type { Team } from "../types/draft";

interface BanRowProps {
  team: Team;
}

function BanRow({ team }: BanRowProps) {
  const session = useDraftStore((s) => s.session);
  const brawlers = useDraftStore((s) => s.brawlers);
  const targetedBanSlot = useDraftStore((s) => s.targetedBanSlot);
  const setTargetedBanSlot = useDraftStore((s) => s.setTargetedBanSlot);
  const clearBanSlot = useDraftStore((s) => s.clearBanSlot);

  if (!session) {
    return null;
  }

  const slots = team === "blue" ? session.blueBans : session.redBans;
  const isBlue = team === "blue";

  return (
    <div className="space-y-2">
      <h3 className={`text-sm font-semibold ${isBlue ? "text-sky-400" : "text-rose-400"}`}>
        {teamLabel(team)} bans
      </h3>
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: BANS_PER_TEAM }, (_, slotIndex) => {
          const brawlerId = slots[slotIndex] ?? null;
          const isTarget =
            targetedBanSlot?.team === team && targetedBanSlot.slotIndex === slotIndex;
          const name = brawlerId != null ? getBrawlerName(brawlers, brawlerId) : null;

          return (
            <button
              key={`${team}-ban-${slotIndex}`}
              type="button"
              onClick={() => setTargetedBanSlot({ team, slotIndex })}
              onContextMenu={(event) => {
                event.preventDefault();
                if (brawlerId != null) {
                  clearBanSlot(team, slotIndex);
                }
              }}
              className={`min-w-[7.5rem] rounded-lg border px-3 py-2 text-left text-sm transition ${
                isTarget
                  ? "border-amber-400 bg-amber-400/10 ring-2 ring-amber-400/40"
                  : isBlue
                    ? "border-sky-800 bg-sky-950/40 hover:border-sky-600"
                    : "border-rose-800 bg-rose-950/40 hover:border-rose-600"
              }`}
            >
              <span className="block text-xs uppercase tracking-wide text-slate-500">
                Ban {slotIndex + 1}
              </span>
              <span className="block truncate font-medium">
                {name ?? "Select slot"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function BanSection() {
  return (
    <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Ban phase</h2>
          <p className="text-sm text-slate-400">
            Fill any ban slot in any order. Same brawler can appear on both teams.
            Right-click a filled slot to clear it.
          </p>
        </div>
      </div>
      <BanRow team="blue" />
      <BanRow team="red" />
    </section>
  );
}
