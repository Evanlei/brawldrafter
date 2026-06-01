import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useDraftStore } from "../store/draftStore";

export function LobbyView() {
  const navigate = useNavigate();
  const lobby = useDraftStore((s) => s.lobby);
  const modes = useDraftStore((s) => s.modes);
  const maps = useDraftStore((s) => s.maps);
  const setMode = useDraftStore((s) => s.setMode);
  const setMap = useDraftStore((s) => s.setMap);
  const setFirstPickTeam = useDraftStore((s) => s.setFirstPickTeam);
  const startDraft = useDraftStore((s) => s.startDraft);

  const filteredMaps = useMemo(
    () =>
      lobby.selectedModeId == null
        ? []
        : maps.filter((map) => map.modeId === lobby.selectedModeId),
    [maps, lobby.selectedModeId],
  );

  const canStart = lobby.selectedModeId != null && lobby.selectedMapId != null;

  const handleStart = () => {
    if (startDraft()) {
      navigate("/draft");
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-4 py-10">
      <header className="mb-8 text-center">
        <p className="text-sm uppercase tracking-[0.2em] text-sky-400">BrawlDrafter</p>
        <h1 className="mt-2 text-3xl font-bold text-white">Draft lobby</h1>
        <p className="mt-2 text-slate-400">
          Choose mode and map before entering the ban and pick flow.
        </p>
      </header>

      <div className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl shadow-black/20">
        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-300">Game mode</span>
          <select
            value={lobby.selectedModeId ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              setMode(value ? Number(value) : null);
            }}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-white focus:border-sky-500 focus:outline-none"
          >
            <option value="">Select a mode</option>
            {modes.map((mode) => (
              <option key={mode.modeId} value={mode.modeId}>
                {mode.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-300">Map</span>
          <select
            value={lobby.selectedMapId ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              setMap(value ? Number(value) : null);
            }}
            disabled={lobby.selectedModeId == null}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-white enabled:focus:border-sky-500 enabled:focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            <option value="">
              {lobby.selectedModeId == null ? "Select a mode first" : "Select a map"}
            </option>
            {filteredMaps.map((map) => (
              <option key={map.mapId} value={map.mapId}>
                {map.name}
              </option>
            ))}
          </select>
        </label>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-300">First pick team</legend>
          <div className="flex gap-3">
            {(["blue", "red"] as const).map((team) => (
              <label
                key={team}
                className={`flex flex-1 cursor-pointer items-center justify-center rounded-lg border px-3 py-2.5 text-sm capitalize ${
                  lobby.firstPickTeam === team
                    ? team === "blue"
                      ? "border-sky-500 bg-sky-950/50 text-sky-200"
                      : "border-rose-500 bg-rose-950/50 text-rose-200"
                    : "border-slate-700 bg-slate-950 text-slate-400"
                }`}
              >
                <input
                  type="radio"
                  name="firstPickTeam"
                  value={team}
                  checked={lobby.firstPickTeam === team}
                  onChange={() => setFirstPickTeam(team)}
                  className="sr-only"
                />
                {team}
              </label>
            ))}
          </div>
        </fieldset>

        <button
          type="button"
          disabled={!canStart}
          onClick={handleStart}
          className="w-full rounded-lg bg-sky-500 px-4 py-3 font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          Start draft
        </button>
      </div>
    </div>
  );
}
