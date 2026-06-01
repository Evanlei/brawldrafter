import { BrawlerPortrait } from "./BrawlerPortrait";
import { PICKS_PER_TEAM, teamLabel } from "../constants/draftSteps";
import { getBrawlerName, getCurrentPickStep, isDraftComplete } from "../store/selectors";
import { useDraftStore } from "../store/draftStore";
import type { Team } from "../types/draft";

interface PickRowProps {
  team: Team;
}

function PickRow({ team }: PickRowProps) {
  const session = useDraftStore((s) => s.session);
  const brawlers = useDraftStore((s) => s.brawlers);
  const currentStep = session ? getCurrentPickStep(session) : null;
  const isBlue = team === "blue";

  if (!session) {
    return null;
  }

  const picks = team === "blue" ? session.bluePicks : session.redPicks;

  return (
    <div className="space-y-2">
      <h3 className={`text-sm font-semibold ${isBlue ? "text-sky-400" : "text-rose-400"}`}>
        {teamLabel(team)} picks
      </h3>
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: PICKS_PER_TEAM }, (_, slotIndex) => {
          const brawlerId = picks[slotIndex] ?? null;
          const isActive =
            !isDraftComplete(session) &&
            currentStep?.team === team &&
            currentStep.teamSlot === slotIndex;
          const name = brawlerId != null ? getBrawlerName(brawlers, brawlerId) : null;

          return (
            <div
              key={`${team}-pick-${slotIndex}`}
              className={`flex min-w-[5.5rem] flex-col items-center gap-1.5 rounded-xl border p-2 text-sm ${
                isActive
                  ? "border-amber-400 bg-amber-400/10 ring-2 ring-amber-400/40"
                  : isBlue
                    ? "border-sky-800 bg-sky-950/40"
                    : "border-rose-800 bg-rose-950/40"
              }`}
            >
              {brawlerId != null && name ? (
                <BrawlerPortrait brawlerId={brawlerId} name={name} size="sm" />
              ) : (
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-dashed border-slate-600 text-slate-600">
                  —
                </div>
              )}
              <span className="block text-[10px] uppercase tracking-wide text-slate-500">
                Pick {slotIndex + 1}
              </span>
              <span className="block max-w-full truncate text-xs font-semibold uppercase">
                {name ?? "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PickBoard() {
  const session = useDraftStore((s) => s.session);
  const undoLastPick = useDraftStore((s) => s.undoLastPick);
  const currentStep = session ? getCurrentPickStep(session) : null;
  const complete = session ? isDraftComplete(session) : false;

  return (
    <section className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Pick phase</h2>
          <p className="text-sm text-slate-400">
            {complete
              ? "Draft complete."
              : currentStep
                ? `${teamLabel(currentStep.team)} team is picking.`
                : "Waiting for picks."}
          </p>
        </div>
        {!complete && (
          <button
            type="button"
            onClick={undoLastPick}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500 hover:text-white"
          >
            Undo last pick
          </button>
        )}
      </div>
      <PickRow team="blue" />
      <PickRow team="red" />
    </section>
  );
}
