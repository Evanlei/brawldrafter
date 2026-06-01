#!/usr/bin/env python3
"""Train DraftNet for a single game mode and save the best checkpoint."""

from __future__ import annotations

import argparse
import logging
import random
import sqlite3
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml.dataset import (  # noqa: E402
    DraftDataset,
    MatchRecord,
    augment_to_partial_states,
    load_feature_store,
    load_matches,
)
from ml.features import input_dim  # noqa: E402
from ml.model import DraftNet, save_model  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "brawldrafter.db"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "backend" / "models"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train DraftNet for one game mode.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--mode-id", type=int, required=True)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Checkpoint path (default: backend/models/draftnet_{mode_id}.pt)",
    )
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for match split.")
    parser.add_argument("--patience", type=int, default=5, help="Early stopping patience.")
    parser.add_argument(
        "--aggregate-first",
        action="store_true",
        help="Run aggregation on the DB before training.",
    )
    return parser.parse_args()


def split_matches_by_match(
    matches: list[MatchRecord],
    val_split: float,
    seed: int,
) -> tuple[list[MatchRecord], list[MatchRecord]]:
    """Split at match level so augmented partial states do not leak across splits."""
    if not matches:
        return [], []
    if not 0.0 < val_split < 1.0:
        raise ValueError("--val-split must be between 0 and 1 (exclusive)")

    indices = list(range(len(matches)))
    rng = random.Random(seed)
    rng.shuffle(indices)

    val_count = max(1, int(len(matches) * val_split)) if len(matches) > 1 else 0
    if len(matches) == 1:
        val_count = 0

    val_set = set(indices[:val_count])
    train_matches = [matches[i] for i in range(len(matches)) if i not in val_set]
    val_matches = [matches[i] for i in range(len(matches)) if i in val_set]
    return train_matches, val_matches


def run_epoch(
    model: DraftNet,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
) -> tuple[float, float]:
    is_train = optimizer is not None
    model.train(is_train)
    total_loss = 0.0
    correct = 0
    total = 0

    for features, labels in loader:
        features = features.to(device)
        labels = labels.to(device)

        if is_train:
            optimizer.zero_grad()

        outputs = model(features)
        loss = criterion(outputs, labels)

        if is_train:
            loss.backward()
            optimizer.step()

        batch_size = labels.numel()
        total_loss += float(loss.item()) * batch_size
        preds = (outputs >= 0.5).float()
        correct += int((preds == labels).sum().item())
        total += batch_size

    if total == 0:
        return 0.0, 0.0
    return total_loss / total, correct / total


def main() -> None:
    setup_logging()
    args = parse_args()
    output_path = args.output or (DEFAULT_MODEL_DIR / f"draftnet_{args.mode_id}.pt")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if not args.db_path.exists():
        raise SystemExit(f"Database not found: {args.db_path}")

    if args.aggregate_first:
        from app.services.aggregation import aggregate_database

        logging.info("Running aggregation before training...")
        aggregate_database(args.db_path, mode_id=args.mode_id)

    with sqlite3.connect(args.db_path) as conn:
        store = load_feature_store(conn, args.mode_id)
        matches = load_matches(conn, args.mode_id)

    if not matches:
        raise SystemExit(f"No training matches found for mode_id={args.mode_id}")

    train_matches, val_matches = split_matches_by_match(matches, args.val_split, args.seed)
    train_samples = augment_to_partial_states(train_matches)
    val_samples = augment_to_partial_states(val_matches)

    train_ds = DraftDataset(train_samples, store, args.mode_id)
    val_ds = DraftDataset(val_samples, store, args.mode_id)

    if len(train_ds) == 0:
        raise SystemExit("Training set is empty after augmentation.")

    feature_size = input_dim(store)
    model = DraftNet(feature_size).to(device)
    criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    logging.info(
        "mode_id=%s matches(train/val)=%s/%s samples(train/val)=%s/%s input_dim=%s device=%s",
        args.mode_id,
        len(train_matches),
        len(val_matches),
        len(train_ds),
        len(val_ds),
        feature_size,
        device,
    )

    best_val_loss = float("inf")
    best_val_acc = 0.0
    best_state: dict[str, torch.Tensor] | None = None
    patience_left = args.patience

    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = run_epoch(model, val_loader, criterion, None, device)

        logging.info(
            "epoch=%s train_loss=%.4f train_acc=%.4f val_loss=%.4f val_acc=%.4f",
            epoch,
            train_loss,
            train_acc,
            val_loss,
            val_acc,
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_val_acc = val_acc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience_left = args.patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                logging.info("Early stopping at epoch %s (patience=%s)", epoch, args.patience)
                break

    if best_state is None:
        best_state = model.state_dict()
        best_val_acc = val_acc if len(val_ds) > 0 else train_acc

    model.load_state_dict(best_state)
    save_model(
        output_path,
        model,
        mode_id=args.mode_id,
        metadata={
            "val_loss": best_val_loss,
            "val_accuracy": best_val_acc,
            "train_samples": len(train_ds),
            "val_samples": len(val_ds),
            "match_count_train": len(train_matches),
            "match_count_val": len(val_matches),
            "feature_store": {
                "all_brawler_ids": store.all_brawler_ids,
                "all_map_ids": store.all_map_ids,
                "all_mode_ids": store.all_mode_ids,
            },
        },
    )

    print(
        f"Saved model to {output_path}\n"
        f"Final val accuracy: {best_val_acc:.4f}\n"
        f"Samples: train={len(train_ds)} val={len(val_ds)} "
        f"(matches train={len(train_matches)} val={len(val_matches)})"
    )


if __name__ == "__main__":
    main()
