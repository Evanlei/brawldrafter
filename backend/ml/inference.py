"""DraftNet inference for Mode B recommendation scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from backend.ml.features import DraftState, FeatureStore, build_input_vector, input_dim
from backend.ml.model import DraftNet, load_model


@dataclass
class InferenceModel:
    """Loaded DraftNet checkpoint ready for draft-state scoring."""

    model: DraftNet
    device: torch.device
    mode_id: int
    input_dim: int
    hidden_dim: int
    metadata: dict[str, Any]
    feature_store_metadata: dict[str, Any] | None = None

    def predict_batch(self, feature_matrix: np.ndarray) -> np.ndarray:
        """Run forward pass on a batch of feature vectors; returns win probabilities."""
        if feature_matrix.size == 0:
            return np.array([], dtype=np.float32)

        expected = self.input_dim
        if feature_matrix.shape[1] != expected:
            raise ValueError(
                f"Feature width {feature_matrix.shape[1]} does not match model input_dim {expected}"
            )

        tensor = torch.from_numpy(feature_matrix.astype(np.float32, copy=False)).to(self.device)
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(tensor)
        return outputs.detach().cpu().numpy().astype(np.float32, copy=False)


def _extract_feature_store_metadata(payload: dict[str, Any]) -> dict[str, Any] | None:
    nested = payload.get("feature_store")
    if isinstance(nested, dict):
        return nested
    if "all_brawler_ids" in payload:
        return {
            "all_brawler_ids": payload.get("all_brawler_ids"),
            "all_map_ids": payload.get("all_map_ids"),
            "all_mode_ids": payload.get("all_mode_ids"),
        }
    return None


def load_inference_model(
    model_path: str | Path,
    device: str | torch.device | None = None,
) -> InferenceModel:
    """Load DraftNet and checkpoint metadata from a .pt file (eval mode)."""
    resolved_device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model, payload = load_model(model_path, device=resolved_device)
    model.eval()

    metadata = {
        k: v
        for k, v in payload.items()
        if k not in {"state_dict", "input_dim", "hidden_dim", "mode_id"}
    }

    return InferenceModel(
        model=model,
        device=resolved_device,
        mode_id=int(payload["mode_id"]),
        input_dim=int(payload["input_dim"]),
        hidden_dim=int(payload.get("hidden_dim", model.hidden_dim)),
        metadata=metadata,
        feature_store_metadata=_extract_feature_store_metadata(payload),
    )


def rank_candidates(
    model: InferenceModel,
    blue_picks: list[int],
    red_picks: list[int],
    available_brawlers: list[int],
    map_id: int,
    mode_id: int,
    feature_store: FeatureStore,
) -> list[tuple[int, float]]:
    """
    Score each available brawler as the next blue pick; return (id, win_probability)
    sorted by probability descending.
    """
    if model.mode_id != mode_id:
        raise ValueError(
            f"Inference model mode_id={model.mode_id} does not match request mode_id={mode_id}"
        )

    expected_dim = input_dim(feature_store)
    if model.input_dim != expected_dim:
        raise ValueError(
            f"Model input_dim={model.input_dim} does not match feature_store dim={expected_dim}"
        )

    blue_set = set(blue_picks)
    red_set = set(red_picks)
    candidate_ids: list[int] = []
    vectors: list[np.ndarray] = []

    for brawler_id in available_brawlers:
        if brawler_id in blue_set or brawler_id in red_set:
            continue

        state = DraftState(
            blue_picks=[*blue_picks, brawler_id],
            red_picks=red_picks,
            map_id=map_id,
            mode_id=mode_id,
        )
        candidate_ids.append(brawler_id)
        vectors.append(build_input_vector(state, feature_store))

    if not candidate_ids:
        return []

    feature_matrix = np.stack(vectors, axis=0)
    probabilities = model.predict_batch(feature_matrix)
    ranked = sorted(
        zip(candidate_ids, probabilities.tolist()),
        key=lambda row: row[1],
        reverse=True,
    )
    return [(brawler_id, float(prob)) for brawler_id, prob in ranked]


__all__ = ["InferenceModel", "load_inference_model", "rank_candidates"]
