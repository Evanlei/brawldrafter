import { useEffect, useMemo } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { BanSection } from "../components/BanSection";
import { BrawlerGrid } from "../components/BrawlerGrid";
import { PickBoard } from "../components/PickBoard";
import { RecommendationsSidebar } from "../components/RecommendationsSidebar";
import {
  isBanPhaseComplete,
  isDraftComplete,
  shouldFetchRecommendations,
  toRecommendationPayload,
} from "../store/selectors";
import { useDraftStore } from "../store/draftStore";

export function DraftView() {
  const navigate = useNavigate();
  const session = useDraftStore((s) => s.session);
  const continueToPicks = useDraftStore((s) => s.continueToPicks);
  const resetDraft = useDraftStore((s) => s.resetDraft);
  const fetchRecommendations = useDraftStore((s) => s.fetchRecommendations);

  const recommendationKey = useMemo(
    () => (session ? JSON.stringify(toRecommendationPayload(session)) : null),
    [session],
  );

  useEffect(() => {
    if (session && shouldFetchRecommendations(session)) {
      fetchRecommendations();
    }
  }, [recommendationKey, session, fetchRecommendations]);

  if (!session) {
    return <Navigate to="/" replace />;
  }

  const bansComplete = isBanPhaseComplete(session);
  const draftComplete = isDraftComplete(session);

  return (
    <div className="mx-auto flex min-h-screen max-w-[90rem] flex-col bg-slate-950 px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-sky-400">Live draft</p>
          <h1 className="text-2xl font-bold text-white">
            {session.modeLabel} · {session.mapName}
          </h1>
          <p className="text-sm text-slate-400">
            {session.subPhase === "bans"
              ? "Ban phase — no turn order"
              : draftComplete
                ? "Draft complete"
                : "Pick phase — snake draft"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              resetDraft();
              navigate("/");
            }}
            className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-slate-500 hover:text-white"
          >
            Exit draft
          </button>
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-4 lg:flex-row">
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          {session.subPhase === "bans" ? <BanSection /> : <PickBoard />}
          <BrawlerGrid />
        </div>
        <RecommendationsSidebar />
      </div>

      {session.subPhase === "bans" && (
        <div className="sticky bottom-4 mt-4 flex justify-end">
          <button
            type="button"
            disabled={!bansComplete}
            onClick={continueToPicks}
            className="rounded-lg bg-amber-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          >
            Continue to picks
          </button>
        </div>
      )}
    </div>
  );
}
