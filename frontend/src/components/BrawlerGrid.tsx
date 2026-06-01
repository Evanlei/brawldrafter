import { useMemo, useState } from "react";

import { getAvailableBrawlers } from "../store/selectors";
import { useDraftStore } from "../store/draftStore";

export function BrawlerGrid() {
  const session = useDraftStore((s) => s.session);
  const brawlers = useDraftStore((s) => s.brawlers);
  const targetedBanSlot = useDraftStore((s) => s.targetedBanSlot);
  const assignBan = useDraftStore((s) => s.assignBan);
  const selectBrawlerForPick = useDraftStore((s) => s.selectBrawlerForPick);
  const [query, setQuery] = useState("");

  const available = useMemo(() => {
    if (!session) {
      return brawlers;
    }
    if (session.subPhase === "bans") {
      return brawlers;
    }
    return getAvailableBrawlers(brawlers, session);
  }, [session, brawlers]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return available;
    }
    return available.filter(
      (b) =>
        b.name.toLowerCase().includes(q) ||
        String(b.brawlerId).includes(q),
    );
  }, [available, query]);

  const handleSelect = (brawlerId: number) => {
    if (!session) {
      return;
    }
    if (session.subPhase === "bans") {
      if (!targetedBanSlot) {
        return;
      }
      assignBan(targetedBanSlot.team, targetedBanSlot.slotIndex, brawlerId);
      return;
    }
    selectBrawlerForPick(brawlerId);
  };

  const helperText =
    session?.subPhase === "bans"
      ? targetedBanSlot
        ? `Assigning to ${targetedBanSlot.team} ban slot ${targetedBanSlot.slotIndex + 1}`
        : "Click a ban slot, then choose a brawler"
      : "Select a brawler for the active pick";

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Brawlers</h2>
          <p className="text-sm text-slate-400">{helperText}</p>
        </div>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search brawlers..."
          className="w-full max-w-xs rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {filtered.map((brawler) => (
            <button
              key={brawler.brawlerId}
              type="button"
              onClick={() => handleSelect(brawler.brawlerId)}
              className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-left text-sm transition hover:border-sky-600 hover:bg-sky-950/30"
            >
              <span className="block truncate font-medium">{brawler.name}</span>
              <span className="block text-xs text-slate-500">#{brawler.brawlerId}</span>
            </button>
          ))}
        </div>
        {filtered.length === 0 && (
          <p className="py-8 text-center text-sm text-slate-500">No brawlers match your search.</p>
        )}
      </div>
    </section>
  );
}
