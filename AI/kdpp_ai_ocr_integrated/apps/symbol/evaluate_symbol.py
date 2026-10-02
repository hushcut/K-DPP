from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from apps.symbol.data_quality import assert_no_split_leakage
from apps.symbol.dataset_csv import SymbolCsvDataset
from apps.symbol.metrics import apply_thresholds, compute_multilabel_metrics
from apps.symbol.model_io import build_evaluation_transform, load_symbol_model


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="세탁기호 멀티라벨 모델 평가"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--split",
        default="valid",
        choices=["train", "valid", "test"],
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument(
        "--device",
        default="cuda" if torch.cuda.is_available() else "cpu",
    )
    return parser.parse_args()


def sanitize_csv_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: sanitize_csv_cell(row.get(key, ""))
                    for key in fieldnames
                }
            )


def existing_splits(data_dir: Path) -> tuple[str, ...]:
    return tuple(
        split
        for split in ("train", "valid", "test")
        if (data_dir / split / "_classes.csv").is_file()
    )


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size는 1 이상이어야 합니다.")

    data_dir = Path(args.data_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()
    device = torch.device(args.device)

    splits = existing_splits(data_dir)
    if len(splits) > 1:
        print("[Hard gate] split leakage check")
        assert_no_split_leakage(data_dir, splits)

    dataset = SymbolCsvDataset(
        str(data_dir / args.split),
        transform=build_evaluation_transform(),
    )
    model, class_names, thresholds = load_symbol_model(
        str(model_path),
        device=device,
    )
    if dataset.class_names != class_names:
        raise ValueError(
            "평가 CSV 클래스 컬럼과 모델 class_names의 값 또는 순서가 다릅니다."
        )

    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=args.workers > 0,
    )

    probability_batches: list[np.ndarray] = []
    target_batches: list[np.ndarray] = []
    image_paths: list[str] = []
    with torch.inference_mode():
        for images, labels, paths in loader:
            probabilities = torch.sigmoid(
                model(images.to(device, non_blocking=True))
            )
            probability_batches.append(probabilities.cpu().numpy())
            target_batches.append(labels.numpy())
            image_paths.extend(paths)

    probabilities = np.concatenate(probability_batches, axis=0)
    targets = np.concatenate(target_batches, axis=0)
    predictions = apply_thresholds(probabilities, thresholds)
    metrics = compute_multilabel_metrics(targets, predictions)

    class_rows: list[dict] = []
    for class_name, threshold, row in zip(
        class_names,
        thresholds,
        metrics.per_class,
    ):
        class_rows.append(
            {
                "class": class_name,
                "threshold": threshold,
                **row,
            }
        )

    wrong_rows: list[dict] = []
    for image_path, target, prediction, scores in zip(
        image_paths,
        targets,
        predictions,
        probabilities,
    ):
        if np.array_equal(target, prediction):
            continue
        true_indices = np.flatnonzero(target)
        predicted_indices = np.flatnonzero(prediction)
        score_indices = np.argsort(scores)[::-1][:8]
        wrong_rows.append(
            {
                "image_path": image_path,
                "true_classes": "; ".join(
                    class_names[index] for index in true_indices
                ),
                "predicted_classes": "; ".join(
                    class_names[index] for index in predicted_indices
                ),
                "false_positives": "; ".join(
                    class_names[index]
                    for index in predicted_indices
                    if not target[index]
                ),
                "false_negatives": "; ".join(
                    class_names[index]
                    for index in true_indices
                    if not prediction[index]
                ),
                "top_scores": "; ".join(
                    f"{class_names[index]}={scores[index]:.4f}"
                    for index in score_indices
                ),
            }
        )

    metrics_path = output_dir / f"{args.split}_class_metrics.csv"
    wrong_path = output_dir / f"{args.split}_wrong_predictions.csv"
    summary_path = output_dir / f"{args.split}_evaluation_summary.json"
    write_csv(
        metrics_path,
        [
            "class",
            "threshold",
            "precision",
            "recall",
            "f1",
            "support",
            "predicted_positive",
            "tp",
            "fp",
            "fn",
            "tn",
        ],
        class_rows,
    )
    write_csv(
        wrong_path,
        [
            "image_path",
            "true_classes",
            "predicted_classes",
            "false_positives",
            "false_negatives",
            "top_scores",
        ],
        wrong_rows,
    )
    summary_path.write_text(
        json.dumps(
            {
                "model": str(model_path),
                "split": args.split,
                "thresholds": dict(zip(class_names, thresholds)),
                "metrics": metrics.to_dict(),
                "wrong_prediction_count": len(wrong_rows),
                "dataset_audit": {
                    "csv_rows": dataset.audit.csv_rows,
                    "loaded_rows": dataset.audit.loaded_rows,
                    "all_negative_rows": dataset.audit.all_negative_rows,
                },
                "notes": {
                    "hamming_accuracy": (
                        "true negative가 많은 희소 멀티라벨 문제에서 "
                        "과대평가되므로 참고 지표로만 사용"
                    ),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Macro-F1 (observed): {metrics.macro_f1_observed:.4f}\n"
        f"Micro-F1: {metrics.micro_f1:.4f}\n"
        f"Micro precision: {metrics.micro_precision:.4f}\n"
        f"Micro recall: {metrics.micro_recall:.4f}\n"
        f"Exact match: {metrics.exact_match:.4f}\n"
        f"Hamming accuracy (diagnostic only): "
        f"{metrics.hamming_accuracy:.4f}"
    )
    print("[Classes with support or predicted positives]")
    for row in class_rows:
        if row["support"] or row["predicted_positive"]:
            print(
                f"  {row['class']}: "
                f"P={row['precision']:.4f}, "
                f"R={row['recall']:.4f}, "
                f"F1={row['f1']:.4f}, "
                f"support={row['support']}, "
                f"predicted={row['predicted_positive']}"
            )
    print(f"Class metrics: {metrics_path}")
    print(f"Wrong predictions: {wrong_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
