"""Minimal Brawl Stars API client for catalog bootstrap."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.brawlstars.com/v1"


class BrawlStarsClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.BRAWLSTARS_API_KEY

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def get_json(self, path: str, *, timeout: float = 20.0) -> dict[str, Any]:
        url = f"{API_BASE}{path}"
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected response type from {path}")
        return payload

    def list_brawlers(self) -> list[dict[str, Any]]:
        payload = self.get_json("/brawlers")
        items = payload.get("items")
        if not isinstance(items, list):
            raise RuntimeError("Brawl Stars /brawlers response missing items list")
        return [item for item in items if isinstance(item, dict)]


def fetch_brawler_name_map() -> dict[int, str]:
    """Return brawler id -> display name from the official API."""
    client = BrawlStarsClient()
    names: dict[int, str] = {}
    for item in client.list_brawlers():
        brawler_id = item.get("id")
        name = item.get("name")
        if isinstance(brawler_id, int) and isinstance(name, str) and name.strip():
            names[brawler_id] = name.strip()
    logger.info("Fetched %s brawler names from Brawl Stars API", len(names))
    return names


__all__ = ["BrawlStarsClient", "fetch_brawler_name_map"]
