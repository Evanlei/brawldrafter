"""DraftNet architecture and checkpoint I/O."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
import torch.nn as nn


class DraftNet(nn.Module):
    """Predicts blue-team win probability from a draft feature vector."""

    def __init__(self, input_dim: int, hidden_dim: int = 128) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def save_model(
    path: str | Path,
    model: DraftNet,
    *,
    mode_id: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist model weights and training metadata."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "state_dict": model.state_dict(),
        "input_dim": model.input_dim,
        "hidden_dim": model.hidden_dim,
        "mode_id": mode_id,
    }
    if metadata:
        payload.update(metadata)
    torch.save(payload, out)


def load_model(path: str | Path, device: str | torch.device = "cpu") -> tuple[DraftNet, dict[str, Any]]:
    """Load a checkpoint saved by save_model."""
    payload = torch.load(Path(path), map_location=device, weights_only=False)
    model = DraftNet(
        input_dim=int(payload["input_dim"]),
        hidden_dim=int(payload.get("hidden_dim", 128)),
    )
    model.load_state_dict(payload["state_dict"])
    model.to(device)
    model.eval()
    return model, payload


__all__ = ["DraftNet", "load_model", "save_model"]
