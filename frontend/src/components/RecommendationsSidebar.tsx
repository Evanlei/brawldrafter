import { BrawlerPortrait } from "./BrawlerPortrait";
import { formatWinRate } from "../constants/draftSteps";
import { shouldFetchRecommendations } from "../store/selectors";
import { useDraftStore } from "../store/draftStore";

function displayWinRate(mapWinRate: number, pickScore: number): { label: string; value: string } {
  if (mapWinRate > 0) {
    return { label: "Map win rate", value: formatWinRate(mapWinRate) };
  }
  return { label: "Pick fit", value: formatWinRate(pickScore) };
}

export function RecommendationsSidebar() {
  const session = useDraftStore((s) => s.session);
  const recommendations = useDraftStore((s) => s.recommendations);
  const fetchRecommendations = useDraftStore((s) => s.fetchRecommendations);
  const selectBrawlerForPick = useDraftStore((s) => s.selectBrawlerForPick);

  if (!session) {
    return null;
  }

  const canRecommend = shouldFetchRecommendations(session);

  return (
    <aside className="flex w-full flex-col rounded-xl border border-slate-800 bg-gradient-to-b from-slate-900/90 to-slate-950/90 p-4 shadow-lg shadow-black/25 lg:w-80 lg:shrink-0">
      <div className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-white">Recommendations</h2>
          <p className="text-xs text-slate-400">Blue pick suggestions — tap to draft</p>
        </div>
        {canRecommend && (
          <button
            type="button"
            onClick={fetchRecommendations}
            className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 transition hover:border-sky-500/50 hover:text-white"
          >
            Refresh
          </button>
        )}
      </div>

      {session.subPhase === "bans" && (
        <p className="rounded-lg border border-dashed border-slate-700 bg-slate-950/50 p-4 text-sm text-slate-400">
          Complete all six bans and continue to picks to load recommendations.
        </p>
      )}

      {session.subPhase === "picks" && !canRecommend && (
        <p className="rounded-lg border border-dashed border-slate-700 bg-slate-950/50 p-4 text-sm text-slate-400">
          {session.bluePicks.length === 3
            ? "All blue picks are in. Recommendations appear on blue pick turns."
            : "Waiting for blue pick turn or draft is complete."}
        </p>
      )}

      {canRecommend && recommendations.status === "loading" && (
        <p className="animate-pulse text-sm text-slate-400">Loading recommendations…</p>
      )}

      {canRecommend && recommendations.status === "error" && (
        <div className="rounded-lg border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-200">
          {recommendations.error ?? "Could not load recommendations."}
        </div>
      )}

      {canRecommend && recommendations.status === "success" && (
        <ul className="space-y-3">
          {recommendations.items.map((item, index) => {
            const stat = displayWinRate(item.mapWinRate, item.pickScore);
            return (
              <li key={item.brawlerId}>
                <button
                  type="button"
                  onClick={() => selectBrawlerForPick(item.brawlerId)}
                  className="flex w-full gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-left transition hover:border-sky-500/50 hover:bg-slate-900"
                >
                  <BrawlerPortrait brawlerId={item.brawlerId} name={item.name} size="lg" />
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-start justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wide text-amber-400">
                        #{index + 1}
                      </span>
                      <div className="text-right">
                        <p className="text-lg font-bold leading-none text-sky-300">{stat.value}</p>
                        <p className="text-[10px] uppercase tracking-wide text-slate-500">
                          {stat.label}
                        </p>
                      </div>
                    </div>
                    <p className="truncate font-semibold text-white">{item.name}</p>
                    <p className="mt-1 text-xs leading-relaxed text-slate-400">{item.reason}</p>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
