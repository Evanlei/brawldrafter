"""DraftNet model runtime tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from app.services.model_runtime import (
    clear_inference_cache,
    get_inference_model,
    has_draftnet_model,
    loaded_mode_ids,
)
from ml.features import FeatureStore
from ml.inference import load_inference_model
from ml.model import DraftNet, save_model


def _minimal_store() -> FeatureStore:
    return FeatureStore(
        all_brawler_ids=[1, 2, 3, 4, 5],
        all_map_ids=[1],
        all_mode_ids=[1],
        counter_scores={(1, 9, 1): 0.15},
        synergy_scores={(1, 2, 1): 0.1},
        win_rates={(1, 1): 0.62, (2, 1): 0.55},
    )


def test_save_and_load_valid_checkpoint(tmp_path: Path) -> None:
    store = _minimal_store()
    from ml.features import input_dim

    dim = input_dim(store)
    model = DraftNet(dim)
    path = tmp_path / "draftnet_1.pt"
    save_model(
        path,
        model,
        mode_id=1,
        metadata={"feature_store": {
            "all_brawler_ids": store.all_brawler_ids,
            "all_map_ids": store.all_map_ids,
            "all_mode_ids": store.all_mode_ids,
        }},
    )

    loaded = load_inference_model(path, device="cpu")
    assert loaded.mode_id == 1
    assert loaded.input_dim == dim
    assert loaded.model.training is False


def test_load_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pt"
    with pytest.raises(FileNotFoundError):
        load_inference_model(missing)


def test_inference_output_shape(tmp_path: Path) -> None:
    store = _minimal_store()
    from ml.features import build_input_vector, DraftState, input_dim

    model = DraftNet(input_dim(store))
    path = tmp_path / "draftnet_1.pt"
    save_model(path, model, mode_id=1)

    inference = load_inference_model(path)
    state = DraftState(blue_picks=[1], red_picks=[9], map_id=1, mode_id=1)
    vector = build_input_vector(state, store)
    probs = inference.predict_batch(vector.reshape(1, -1))
    assert probs.shape == (1,)
    assert 0.0 <= float(probs[0]) <= 1.0


def test_runtime_cache_loads_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_inference_cache()
    store = _minimal_store()
    from ml.features import input_dim

    model = DraftNet(input_dim(store))
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    path = models_dir / "draftnet_7.pt"
    save_model(path, model, mode_id=7)

    monkeypatch.setattr("app.services.model_runtime.MODELS_DIR", models_dir)

    assert has_draftnet_model(7)
    first = get_inference_model(7)
    second = get_inference_model(7)
    assert first is second
    assert loaded_mode_ids() == [7]
    clear_inference_cache()


def test_corrupt_checkpoint_raises(tmp_path: Path) -> None:
    bad = tmp_path / "draftnet_1.pt"
    bad.write_bytes(b"not-a-torch-file")
    with pytest.raises(Exception):
        load_inference_model(bad)
