"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import settings


def verify_internal_api_key(
    x_internal_api_key: Optional[str] = Header(default=None, alias="X-Internal-Api-Key"),
) -> None:
    if not x_internal_api_key or x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")
