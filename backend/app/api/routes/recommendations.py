"""Recommendation API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.services.recommendation import (
    RecommendationRequest,
    get_recommendations,
)
from app.services.recommendation_errors import (
    InsufficientCandidatesError,
    ModelUnavailableError,
    RecommendationError,
)

router = APIRouter(prefix="/api/v1", tags=["recommendations"])
limiter = Limiter(key_func=get_remote_address)


class RecommendationRequestBody(BaseModel):
    map_id: int = Field(..., ge=1)
    mode_id: int = Field(..., ge=1)
    first_pick_team: Literal["blue", "red"]
    blue_bans: list[int] = Field(default_factory=list)
    red_bans: list[int] = Field(default_factory=list)
    blue_picks: list[int] = Field(default_factory=list)
    red_picks: list[int] = Field(default_factory=list)
    current_pick_number: int = Field(..., ge=1, le=6)


class RecommendationItemResponse(BaseModel):
    brawler_id: int
    name: str
    map_win_rate: float
    pick_score: float
    reason: str


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItemResponse]


@router.post("/recommendations", response_model=RecommendationResponse)
@limiter.limit(settings.RATE_LIMIT_RECOMMENDATIONS)
def create_recommendations(
    request: Request,
    body: RecommendationRequestBody,
) -> RecommendationResponse:
    draft_request = RecommendationRequest(
        map_id=body.map_id,
        mode_id=body.mode_id,
        first_pick_team=body.first_pick_team,
        blue_bans=body.blue_bans,
        red_bans=body.red_bans,
        blue_picks=body.blue_picks,
        red_picks=body.red_picks,
        current_pick_number=body.current_pick_number,
    )
    try:
        items = get_recommendations(draft_request)
    except InsufficientCandidatesError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Recommendation model unavailable",
        ) from exc
    except RecommendationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Recommendation service unavailable",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Recommendation service unavailable",
        ) from exc

    if len(items) < 3:
        raise HTTPException(
            status_code=422,
            detail="Insufficient candidates for recommendations",
        )

    return RecommendationResponse(
        recommendations=[
            RecommendationItemResponse(
                brawler_id=item.brawler_id,
                name=item.name,
                map_win_rate=item.map_win_rate,
                pick_score=item.pick_score,
                reason=item.reason,
            )
            for item in items[:3]
        ]
    )
