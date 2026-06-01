"""Internal pipeline triggers (protected by INTERNAL_API_KEY)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import verify_internal_api_key
from app.services.aggregation import AggregationResult
from app.services.brawler_bootstrap import sync_brawler_names
from app.services.pipeline import (
    PipelineRunResult,
    run_aggregate,
    run_fetch,
    run_full_pipeline,
    run_train_all_modes,
)

router = APIRouter(
    prefix="/api/v1/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_api_key)],
)


class FetchRequest(BaseModel):
    players: int = Field(default=50, ge=1, le=500)
    matches_per_player: int = Field(default=25, ge=1, le=100)


class AggregateRequest(BaseModel):
    mode_id: Optional[int] = Field(default=None, ge=1)


class PipelineRequest(BaseModel):
    fetch: bool = True
    aggregate: bool = True
    retrain: bool = False
    players: int = Field(default=50, ge=1, le=500)
    matches_per_player: int = Field(default=25, ge=1, le=100)
    mode_id: Optional[int] = Field(default=None, ge=1)


class TrainRequest(BaseModel):
    min_matches: int = Field(default=100, ge=10)


class StatusResponse(BaseModel):
    status: Literal["ok"] = "ok"
    detail: Optional[str] = None


class AggregateResponse(BaseModel):
    status: Literal["ok"] = "ok"
    match_count: int
    mode_ids: list[int]
    brawler_stats_rows: int
    counter_rows: int
    synergy_rows: int
    snapshot_id: int


class PipelineResponse(BaseModel):
    status: Literal["ok"] = "ok"
    fetch_ran: bool
    brawlers_synced: int
    trained_mode_ids: list[int]
    train_failures: list[int]
    match_count: Optional[int] = None


def _aggregate_response(result: AggregationResult) -> AggregateResponse:
    return AggregateResponse(
        match_count=result.match_count,
        mode_ids=result.mode_ids,
        brawler_stats_rows=result.brawler_stats_rows,
        counter_rows=result.counter_rows,
        synergy_rows=result.synergy_rows,
        snapshot_id=result.snapshot_id,
    )


@router.post("/fetch", response_model=StatusResponse)
def trigger_fetch(body: FetchRequest) -> StatusResponse:
    run_fetch(players=body.players, matches_per_player=body.matches_per_player)
    return StatusResponse(detail="Fetch completed")


@router.post("/aggregate", response_model=AggregateResponse)
def trigger_aggregate(body: AggregateRequest) -> AggregateResponse:
    result = run_aggregate(mode_id=body.mode_id)
    return _aggregate_response(result)


@router.post("/bootstrap-brawlers", response_model=StatusResponse)
def trigger_brawler_bootstrap() -> StatusResponse:
    count = sync_brawler_names()
    return StatusResponse(detail=f"Synced {count} brawler names")


@router.post("/train", response_model=PipelineResponse)
def trigger_train(body: TrainRequest) -> PipelineResponse:
    trained, failures = run_train_all_modes(min_matches=body.min_matches)
    return PipelineResponse(
        fetch_ran=False,
        brawlers_synced=0,
        trained_mode_ids=trained,
        train_failures=failures,
    )


@router.post("/pipeline", response_model=PipelineResponse)
def trigger_pipeline(body: PipelineRequest) -> PipelineResponse:
    result: PipelineRunResult = run_full_pipeline(
        fetch=body.fetch,
        aggregate=body.aggregate,
        retrain=body.retrain,
        players=body.players,
        matches_per_player=body.matches_per_player,
        mode_id=body.mode_id,
    )
    match_count = result.aggregate.match_count if result.aggregate else None
    return PipelineResponse(
        fetch_ran=result.fetch_ran,
        brawlers_synced=result.brawlers_synced,
        trained_mode_ids=result.trained_mode_ids,
        train_failures=result.train_failures,
        match_count=match_count,
    )
