from __future__ import annotations

import argparse
import json
import math
import os
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms

from apps.symbol.data_quality import assert_no_split_leakage
from apps.symbol.dataset_csv import SymbolCsvDataset
from apps.symbol.metrics import (
    apply_thresholds,
    compute_multilabel_metrics,
    tune_class_thresholds,
)
from apps.symbol.model_io import (
    IMAGE_SIZE,
    IMAGENET_MEAN,
    IMAGENET_STD,
    build_evaluation_transform,
    build_resnet18,
    load_symbol_model,
)


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_MODEL_PATH = (
    BASE_DIR / "models" / "symbol" / "best_symbol_model_exp.pt"
)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ResNet18 기반 세탁기호 멀티라벨 모델 학습"
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--model-path", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
    )
    return parser.parse_args()


def set_reproducible_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def seed_worker(worker_id: int) -> None:
    worker_seed = torch.initial_seed() % (2**32)
    np.random.seed(worker_seed)
    random.seed(worker_seed)


def build_transforms() -> tuple[transforms.Compose, transforms.Compose]:
    train_transform = transforms.Compose(
        [
            transforms.Resize((256, 256)),
            transforms.RandomResizedCrop(
                IMAGE_SIZE,
                scale=(0.88, 1.0),
                ratio=(0.90, 1.10),
            ),
            transforms.RandomApply(
                [transforms.RandomRotation(7)],
                p=0.6,
            ),
            transforms.RandomPerspective(
                distortion_scale=0.12,
                p=0.25,
            ),
            transforms.RandomApply(
                [
                    transforms.ColorJitter(
                        brightness=0.22,
                        contrast=0.25,
                    )
                ],
                p=0.65,
            ),
            transforms.RandomApply(
                [transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.8))],
                p=0.18,
            ),
            transforms.RandomGrayscale(p=0.08),
            transforms.ToTensor(),
            transforms.RandomErasing(
                p=0.12,
                scale=(0.01, 0.05),
                ratio=(0.5, 2.0),
                value="random",
            ),
            transforms.Normalize(
                mean=IMAGENET_MEAN,
                std=IMAGENET_STD,
            ),
        ]
    )
    evaluation_transform = build_evaluation_transform()
    return train_transform, evaluation_transform


def compute_pos_weights(
    class_counts: Counter,
    num_classes: int,
    num_samples: int,
    *,
    max_weight: float = 20.0,
) -> torch.Tensor:
    weights: list[float] = []
    for class_index in range(num_classes):
        positives = int(class_counts.get(class_index, 0))
        if positives == 0:
            # A class without a positive training example cannot be learned.
            # Keep its loss neutral and report it in the audit output.
            weights.append(1.0)
            continue
        imbalance = max((num_samples - positives) / positives, 1.0)
        weights.append(min(math.sqrt(imbalance), max_weight))
    return torch.tensor(weights, dtype=torch.float32)


def make_loader(
    dataset: SymbolCsvDataset,
    *,
    batch_size: int,
    shuffle: bool,
    workers: int,
    seed: int,
) -> DataLoader:
    generator = torch.Generator()
    generator.manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=workers,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=workers > 0,
        worker_init_fn=seed_worker if workers > 0 else None,
        generator=generator,
    )


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    *,
    device: torch.device,
    optimizer: optim.Optimizer | None = None,
) -> tuple[float, np.ndarray, np.ndarray]:
    training = optimizer is not None
    model.train(training)

    loss_sum = 0.0
    sample_count = 0
    probability_batches: list[np.ndarray] = []
    target_batches: list[np.ndarray] = []

    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for images, labels, _ in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            if optimizer is not None:
                optimizer.zero_grad(set_to_none=True)

            logits = model(images)
            loss = criterion(logits, labels)

            if optimizer is not None:
                loss.backward()
                optimizer.step()

            batch_size = labels.size(0)
            loss_sum += float(loss.item()) * batch_size
            sample_count += batch_size
            probability_batches.append(
                torch.sigmoid(logits).detach().cpu().numpy()
            )
            target_batches.append(labels.detach().cpu().numpy())

    if sample_count == 0:
        raise ValueError("학습 또는 평가 데이터로더가 비어 있습니다.")
    return (
        loss_sum / sample_count,
        np.concatenate(probability_batches, axis=0),
        np.concatenate(target_batches, axis=0),
    )


def verify_dataset_contract(
    train_dataset: SymbolCsvDataset,
    other_dataset: SymbolCsvDataset,
    other_name: str,
) -> None:
    if train_dataset.class_names != other_dataset.class_names:
        raise ValueError(
            f"train/{other_name} 클래스 컬럼과 순서가 다릅니다. "
            "_classes.csv를 확인하세요."
        )


def metric_summary(metrics: dict) -> str:
    return (
        f"macro_f1={metrics['macro_f1_observed']:.4f}, "
        f"micro_f1={metrics['micro_f1']:.4f}, "
        f"exact={metrics['exact_match']:.4f}"
    )


def main() -> None:
    args = parse_args()
    if args.epochs < 1 or args.patience < 1 or args.batch_size < 1:
        raise ValueError("epochs, patience, batch-size는 1 이상이어야 합니다.")

    set_reproducible_seed(args.seed)
    device = torch.device(args.device)
    data_dir = Path(args.data_dir).expanduser().resolve()
    model_path = Path(args.model_path).expanduser().resolve()
    train_dir = data_dir / "train"
    valid_dir = data_dir / "valid"
    test_dir = data_dir / "test"

    leakage_splits = ["train", "valid"]
    if (test_dir / "_classes.csv").is_file():
        leakage_splits.append("test")
    print("[Hard gate] split leakage check")
    assert_no_split_leakage(data_dir, tuple(leakage_splits))

    train_transform, evaluation_transform = build_transforms()
    train_dataset = SymbolCsvDataset(
        str(train_dir),
        transform=train_transform,
    )
    valid_dataset = SymbolCsvDataset(
        str(valid_dir),
        transform=evaluation_transform,
    )
    verify_dataset_contract(train_dataset, valid_dataset, "valid")

    test_dataset: SymbolCsvDataset | None = None
    if (test_dir / "_classes.csv").is_file():
        test_dataset = SymbolCsvDataset(
            str(test_dir),
            transform=evaluation_transform,
        )
        verify_dataset_contract(train_dataset, test_dataset, "test")

    class_names = train_dataset.class_names
    class_counts = train_dataset.class_counts()
    missing_positive_classes = [
        name
        for index, name in enumerate(class_names)
        if class_counts.get(index, 0) == 0
    ]
    if missing_positive_classes:
        print(
            "[Warning] no positive train samples: "
            + ", ".join(missing_positive_classes)
        )

    print(f"DEVICE: {device}")
    print(
        f"Train: {len(train_dataset)} "
        f"(all-negative={train_dataset.audit.all_negative_rows})"
    )
    print(
        f"Valid: {len(valid_dataset)} "
        f"(all-negative={valid_dataset.audit.all_negative_rows})"
    )
    if test_dataset is not None:
        print(
            f"Test: {len(test_dataset)} "
            f"(all-negative={test_dataset.audit.all_negative_rows})"
        )

    train_loader = make_loader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        workers=args.workers,
        seed=args.seed,
    )
    valid_loader = make_loader(
        valid_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        workers=args.workers,
        seed=args.seed,
    )

    model = build_resnet18(
        len(class_names),
        pretrained=True,
        dropout=args.dropout,
    ).to(device)
    positive_weights = compute_pos_weights(
        class_counts,
        len(class_names),
        len(train_dataset),
    ).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=positive_weights)
    optimizer = optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="max",
        factor=0.5,
        patience=2,
        min_lr=1e-6,
    )

    model_path.parent.mkdir(parents=True, exist_ok=True)
    best_rank = (-1.0, -1.0, -1.0, float("-inf"))
    best_epoch = 0
    epochs_without_improvement = 0

    for epoch in range(1, args.epochs + 1):
        train_loss, train_probabilities, train_targets = run_epoch(
            model,
            train_loader,
            criterion,
            device=device,
            optimizer=optimizer,
        )
        valid_loss, valid_probabilities, valid_targets = run_epoch(
            model,
            valid_loader,
            criterion,
            device=device,
        )

        thresholds = tune_class_thresholds(
            valid_probabilities,
            valid_targets,
        )
        train_metrics = compute_multilabel_metrics(
            train_targets,
            apply_thresholds(train_probabilities, 0.5),
        ).to_dict()
        valid_metrics = compute_multilabel_metrics(
            valid_targets,
            apply_thresholds(valid_probabilities, thresholds),
        ).to_dict()

        scheduler.step(valid_metrics["macro_f1_observed"])
        print(
            f"Epoch {epoch:02d}/{args.epochs} | "
            f"train_loss={train_loss:.4f}, {metric_summary(train_metrics)} | "
            f"valid_loss={valid_loss:.4f}, {metric_summary(valid_metrics)}"
        )

        rank = (
            round(valid_metrics["macro_f1_observed"], 12),
            round(valid_metrics["micro_f1"], 12),
            round(valid_metrics["exact_match"], 12),
            -valid_loss,
        )
        if rank > best_rank:
            best_rank = rank
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "class_names": list(class_names),
                    "thresholds": [float(value) for value in thresholds],
                    "validation_metrics": valid_metrics,
                    "config": {
                        "image_size": IMAGE_SIZE,
                        "resize_size": 256,
                        "batch_size": args.batch_size,
                        "learning_rate": args.learning_rate,
                        "weight_decay": args.weight_decay,
                        "dropout": args.dropout,
                        "seed": args.seed,
                        "task": "multi_label",
                        "selection_metric": "macro_f1_observed",
                    },
                    "epoch": epoch,
                },
                str(model_path),
            )
            print(f"  saved: {model_path}")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(
                    f"Early stopping: {args.patience} epochs without "
                    "macro-F1 improvement."
                )
                break

    print(f"Best epoch: {best_epoch}")
    print(
        "Best validation: "
        f"macro_f1={best_rank[0]:.4f}, "
        f"micro_f1={best_rank[1]:.4f}, "
        f"exact={best_rank[2]:.4f}"
    )

    if test_dataset is None:
        return

    test_loader = make_loader(
        test_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        workers=args.workers,
        seed=args.seed,
    )
    best_model, _, best_thresholds = load_symbol_model(
        str(model_path),
        device=device,
    )
    test_loss, test_probabilities, test_targets = run_epoch(
        best_model,
        test_loader,
        criterion,
        device=device,
    )
    test_metrics = compute_multilabel_metrics(
        test_targets,
        apply_thresholds(test_probabilities, best_thresholds),
    ).to_dict()
    print(
        f"[Final test] loss={test_loss:.4f}, {metric_summary(test_metrics)}"
    )
    result_path = model_path.with_suffix(".test_metrics.json")
    result_path.write_text(
        json.dumps(
            {
                "model": str(model_path),
                "thresholds": best_thresholds,
                "metrics": test_metrics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Test metrics: {result_path}")


if __name__ == "__main__":
    main()
