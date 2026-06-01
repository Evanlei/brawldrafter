"""Public catalog API tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_catalog_modes_maps_brawlers(sample_db: Path) -> None:
    client = TestClient(app)

    modes = client.get("/api/v1/modes")
    assert modes.status_code == 200
    payload = modes.json()
    assert len(payload) >= 1
    assert "modeId" in payload[0]

    maps = client.get("/api/v1/maps", params={"modeId": 1})
    assert maps.status_code == 200
    assert all(row["modeId"] == 1 for row in maps.json())

    brawlers = client.get("/api/v1/brawlers")
    assert brawlers.status_code == 200
    assert len(brawlers.json()) >= 1
