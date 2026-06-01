"""Cached DraftNet inference models (lazy-loaded, not reloaded per request)."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from backend.ml.inference import InferenceModel

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
_DRAFTNET_PATTERN = re.compile(r"^draftnet_(\d+)\.pt$")

_cache: dict[int, InferenceModel] = {}
_model_metadata: dict[int, dict[str, Any]] = {}
_load_lock = threading.Lock()
_warmed = False


def draftnet_path(mode_id: int) -> Path:
    return MODELS_DIR / f"draftnet_{mode_id}.pt"


def has_draftnet_model(mode_id: int) -> bool:
    return draftnet_path(mode_id).is_file()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_for_checkpoint(path: Path, mode_id: int) -> dict[str, Any]:
    import torch

    payload: dict[str, Any] = {
        "mode_id": mode_id,
        "path": str(path),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        if isinstance(checkpoint, dict):
            for key in ("val_accuracy", "val_loss", "train_samples", "match_count_train"):
                if key in checkpoint:
                    payload[key] = checkpoint[key]
    except Exception as exc:  # noqa: BLE001
        payload["metadata_error"] = str(exc)
    return payload


def get_inference_model(mode_id: int) -> InferenceModel | None:
    """Return a cached InferenceModel for mode_id, loading once if the file exists."""
    with _load_lock:
        if mode_id in _cache:
            return _cache[mode_id]

        path = draftnet_path(mode_id)
        if not path.is_file():
            return None

        from backend.ml.inference import load_inference_model

        meta = _metadata_for_checkpoint(path, mode_id)
        logger.info(
            "Loading DraftNet mode_id=%s sha256=%s size=%s path=%s",
            mode_id,
            meta["sha256"][:16],
            meta["size_bytes"],
            path,
        )
        model = load_inference_model(path, device=settings.MODEL_DEVICE)
        _cache[mode_id] = model
        _model_metadata[mode_id] = meta
        return model


def warmup_inference_cache() -> None:
    """Eagerly load all draftnet_*.pt checkpoints found at startup."""
    global _warmed
    with _load_lock:
        if _warmed:
            return
        _warmed = True

    if not MODELS_DIR.is_dir():
        logger.info("No models directory at %s; skipping inference warmup", MODELS_DIR)
        return

    for path in sorted(MODELS_DIR.glob("draftnet_*.pt")):
        match = _DRAFTNET_PATTERN.match(path.name)
        if not match:
            continue
        mode_id = int(match.group(1))
        get_inference_model(mode_id)

    if _model_metadata:
        for mode_id, meta in sorted(_model_metadata.items()):
            logger.info(
                "DraftNet ready mode_id=%s sha256=%s val_accuracy=%s",
                mode_id,
                meta.get("sha256", "")[:16],
                meta.get("val_accuracy"),
            )
    logger.info("Inference cache warmed with %s model(s)", len(_cache))


def clear_inference_cache() -> None:
    """Clear cached models (primarily for tests)."""
    global _warmed
    with _load_lock:
        _cache.clear()
        _model_metadata.clear()
        _warmed = False


def loaded_mode_ids() -> list[int]:
    """Return mode ids currently held in the inference cache."""
    with _load_lock:
        return sorted(_cache.keys())


def model_registry() -> dict[int, dict[str, Any]]:
    """Return checksum/metadata for loaded checkpoints."""
    with _load_lock:
        return {mode_id: dict(meta) for mode_id, meta in _model_metadata.items()}


__all__ = [
    "clear_inference_cache",
    "draftnet_path",
    "get_inference_model",
    "has_draftnet_model",
    "loaded_mode_ids",
    "model_registry",
    "warmup_inference_cache",
]
