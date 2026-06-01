"""Public catalog API (modes, maps, brawlers)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.catalog_service import (
    with_catalog_connection,
    list_brawlers,
    list_maps,
    list_modes,
)

router = APIRouter(prefix="/api/v1", tags=["catalog"])


class ModeResponse(BaseModel):
    mode_id: int = Field(..., serialization_alias="modeId")
    name: str
    label: str

    model_config = {"populate_by_name": True}


class MapResponse(BaseModel):
    map_id: int = Field(..., serialization_alias="mapId")
    name: str
    mode_id: int = Field(..., serialization_alias="modeId")

    model_config = {"populate_by_name": True}


class BrawlerResponse(BaseModel):
    brawler_id: int = Field(..., serialization_alias="brawlerId")
    name: str

    model_config = {"populate_by_name": True}


@router.get("/modes", response_model=list[ModeResponse])
def get_modes() -> list[ModeResponse]:
    with with_catalog_connection() as conn:
        rows = list_modes(conn)
    return [
        ModeResponse(mode_id=row.mode_id, name=row.name, label=row.label)
        for row in rows
    ]


@router.get("/maps", response_model=list[MapResponse])
def get_maps(
    mode_id: Optional[int] = Query(default=None, alias="modeId", ge=1),
) -> list[MapResponse]:
    with with_catalog_connection() as conn:
        rows = list_maps(conn, mode_id=mode_id)
    return [
        MapResponse(map_id=row.map_id, name=row.name, mode_id=row.mode_id)
        for row in rows
    ]


@router.get("/brawlers", response_model=list[BrawlerResponse])
def get_brawlers() -> list[BrawlerResponse]:
    with with_catalog_connection() as conn:
        rows = list_brawlers(conn)
    return [
        BrawlerResponse(brawler_id=row.brawler_id, name=row.name)
        for row in rows
    ]
