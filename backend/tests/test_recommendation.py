"""Hybrid recommendation and API endpoint tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.model_runtime import clear_inference_cache
from app.services.recommendation import RecommendationRequest, get_recommendations
from ml.features import FeatureStore, input_dim
from ml.model import DraftNet, save_model


def test_get_recommendations_returns_three(sample_db: Path) -> None:
    request = RecommendationRequest(
        map_id=1,
        mode_id=1,
        first_pick_team="blue",
        blue_bans=[],
        red_bans=[],
        blue_picks=[],
        red_picks=[9],
        current_pick_number=1,
    )
    items = get_recommendations(request)
    assert len(items) == 3
    assert items[0].confidence >= items[1].confidence >= items[2].confidence
    assert all(item.name.startswith("Brawler") or item.name in {"Tara", "Shelly"} for item in items)


def test_deterministic_fallback_without_model(sample_db: Path) -> None:
    clear_inference_cache()
    request = RecommendationRequest(
        map_id=1,
        mode_id=1,
        first_pick_team="blue",
        blue_bans=[2],
        red_bans=[8],
        blue_picks=[5],
        red_picks=[9],
        current_pick_number=2,
    )
    items = get_recommendations(request)
    assert len(items) == 3


def test_nn_path_when_model_present(
    sample_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_inference_cache()
    import sqlite3

    from ml.dataset import load_feature_store

    with sqlite3.connect(sample_db) as conn:
        store = load_feature_store(conn, mode_id=1)

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model = DraftNet(input_dim(store))
    save_model(
        models_dir / "draftnet_1.pt",
        model,
        mode_id=1,
        metadata={
            "feature_store": {
                "all_brawler_ids": store.all_brawler_ids,
                "all_map_ids": store.all_map_ids,
                "all_mode_ids": store.all_mode_ids,
            }
        },
    )
    monkeypatch.setattr("app.services.model_runtime.MODELS_DIR", models_dir)

    request = RecommendationRequest(
        map_id=1,
        mode_id=1,
        first_pick_team="blue",
        blue_bans=[],
        red_bans=[],
        blue_picks=[],
        red_picks=[9],
        current_pick_number=1,
    )
    items = get_recommendations(request)
    assert len(items) == 3


def test_endpoint_success(sample_db: Path) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/recommendations",
        json={
            "map_id": 1,
            "mode_id": 1,
            "first_pick_team": "blue",
            "blue_bans": [],
            "red_bans": [],
            "blue_picks": [],
            "red_picks": [9],
            "current_pick_number": 1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["recommendations"]) == 3


def test_endpoint_validation_error(sample_db: Path) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/recommendations",
        json={
            "map_id": 0,
            "mode_id": 1,
            "first_pick_team": "blue",
            "blue_bans": [],
            "red_bans": [],
            "blue_picks": [],
            "red_picks": [],
            "current_pick_number": 1,
        },
    )
    assert response.status_code == 422


def test_endpoint_insufficient_candidates_returns_422(sample_db: Path) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/recommendations",
        json={
            "map_id": 1,
            "mode_id": 1,
            "first_pick_team": "blue",
            "blue_bans": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            "red_bans": [12, 13, 14, 15],
            "blue_picks": [],
            "red_picks": [],
            "current_pick_number": 1,
        },
    )
    assert response.status_code == 422


def test_alpha_one_matches_deterministic_order(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.services.deterministic import rank_deterministic
    from app.services.recommendation import RecommendationRequest, get_recommendations
    from ml.dataset import load_feature_store

    get_settings.cache_clear()
    monkeypatch.setenv("RECOMMENDER_ALPHA", "1.0")
    refreshed = get_settings()
    monkeypatch.setattr("app.core.config.settings", refreshed)
    monkeypatch.setattr("app.services.recommendation.settings", refreshed)

    import sqlite3

    with sqlite3.connect(sample_db) as conn:
        store = load_feature_store(conn, mode_id=1)

    request = RecommendationRequest(
        map_id=1,
        mode_id=1,
        first_pick_team="blue",
        blue_bans=[],
        red_bans=[],
        blue_picks=[],
        red_picks=[9],
        current_pick_number=1,
    )
    items = get_recommendations(request)
    det = rank_deterministic(
        request.blue_picks,
        request.red_picks,
        [bid for bid in store.all_brawler_ids if bid not in {9}],
        request.map_id,
        store,
        brawler_names={bid: f"Brawler {bid}" for bid in store.all_brawler_ids},
    )
    assert [item.brawler_id for item in items] == [row[0] for row in det[:3]]


def test_alpha_zero_requires_model_returns_503(
    sample_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    clear_inference_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("RECOMMENDER_ALPHA", "0.0")
    refreshed = get_settings()
    monkeypatch.setattr("app.core.config.settings", refreshed)
    monkeypatch.setattr("app.services.recommendation.settings", refreshed)

    client = TestClient(app)
    response = client.post(
        "/api/v1/recommendations",
        json={
            "map_id": 1,
            "mode_id": 1,
            "first_pick_team": "blue",
            "blue_bans": [],
            "red_bans": [],
            "blue_picks": [],
            "red_picks": [9],
            "current_pick_number": 1,
        },
    )
    assert response.status_code == 503


def test_aggregation_populates_stats(sample_db: Path) -> None:
    import sqlite3

    with sqlite3.connect(sample_db) as conn:
        stats_count = conn.execute("SELECT COUNT(*) FROM brawler_stats").fetchone()[0]
        counter_count = conn.execute("SELECT COUNT(*) FROM counters").fetchone()[0]
        synergy_count = conn.execute("SELECT COUNT(*) FROM synergies").fetchone()[0]
        snapshot_count = conn.execute("SELECT COUNT(*) FROM meta_snapshots").fetchone()[0]

    assert stats_count > 0
    assert counter_count > 0
    assert synergy_count > 0
    assert snapshot_count == 1
