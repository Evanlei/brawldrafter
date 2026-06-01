"""Internal pipeline route auth tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_internal_aggregate_requires_key(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.pipeline.sync_brawler_names", lambda: 0)

    client = TestClient(app)
    denied = client.post("/api/v1/internal/aggregate", json={})
    assert denied.status_code == 403

    allowed = client.post(
        "/api/v1/internal/aggregate",
        json={},
        headers={"X-Internal-Api-Key": "test-internal"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["match_count"] > 0
