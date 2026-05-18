import argparse
import csv
import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import models, transforms

from apps.symbol.dataset_csv import SymbolCsvDataset

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
IMG_SIZE = 224


def load_model(model_path: str):
    checkpoint = torch.load(model_path, map_location=DEVICE)
    class_names = checkpoint["class_names"]
    model = models.resnet18(weights=None)
    model.fc = nn.Sequential(
        nn.Dropout(p=0.3),
        nn.Linear(model.fc.in_features, len(class_names)),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(DEVICE)
    model.eval()
    return model, class_names


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--split", default="valid", choices=["train", "valid", "test"])
    args = parser.parse_args()

    eval_tfms = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    split_dir = os.path.join(DATA_DIR, args.split)
    dataset = SymbolCsvDataset(split_dir, transform=eval_tfms)
    model, class_names = load_model(args.model)

    loader = DataLoader(dataset, batch_size=32, shuffle=False)
    num_classes = len(class_names)
    per_class = [
        {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for _ in range(num_classes)
    ]
    wrong_rows = []
    exact_correct = 0
    label_correct = 0
    label_total = 0
    total = 0

    with torch.no_grad():
        for images, labels, paths in loader:
            outputs = model(images.to(DEVICE))
            probs = torch.sigmoid(outputs).cpu()
            preds = (probs >= 0.5).float()

            for label, pred, path, row_probs in zip(labels, preds, paths, probs):
                total += 1
                exact_match = bool(torch.equal(label, pred))
                if exact_match:
                    exact_correct += 1

                label_correct += int((label == pred).sum().item())
                label_total += num_classes

                true_indices = [idx for idx, value in enumerate(label.tolist()) if value == 1.0]
                pred_indices = [idx for idx, value in enumerate(pred.tolist()) if value == 1.0]

                for idx in range(num_classes):
                    truth = label[idx].item() == 1.0
                    guessed = pred[idx].item() == 1.0
                    if truth and guessed:
                        per_class[idx]["tp"] += 1
                    elif not truth and guessed:
                        per_class[idx]["fp"] += 1
                    elif truth and not guessed:
                        per_class[idx]["fn"] += 1
                    else:
                        per_class[idx]["tn"] += 1

                if not exact_match:
                    wrong_rows.append({
                        "image_path": path,
                        "true_class": "; ".join(class_names[idx] for idx in true_indices),
                        "pred_class": "; ".join(class_names[idx] for idx in pred_indices),
                        "confidence": "; ".join(
                            f"{class_names[idx]}={float(row_probs[idx]):.4f}"
                            for idx in pred_indices[:8]
                        ),
                    })

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    metrics_path = os.path.join(OUTPUT_DIR, f"{args.split}_class_metrics.csv")
    wrong_path = os.path.join(OUTPUT_DIR, f"{args.split}_wrong_predictions.csv")

    with open(metrics_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["class", "precision", "recall", "f1", "tp", "fp", "fn", "tn"])
        for class_name, row in zip(class_names, per_class):
            tp, fp, fn, tn = row["tp"], row["fp"], row["fn"], row["tn"]
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            writer.writerow([class_name, precision, recall, f1, tp, fp, fn, tn])

    with open(wrong_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["image_path", "true_class", "pred_class", "confidence"])
        writer.writeheader()
        writer.writerows(wrong_rows)

    print(f"Exact-match accuracy: {exact_correct / total:.4f} ({exact_correct}/{total})")
    print(f"Label-wise accuracy: {label_correct / label_total:.4f} ({label_correct}/{label_total})")
    print("[Class metrics with positive samples]")
    for class_name, row in zip(class_names, per_class):
        positives = row["tp"] + row["fn"]
        if positives:
            recall = row["tp"] / positives
            precision = row["tp"] / (row["tp"] + row["fp"]) if row["tp"] + row["fp"] else 0.0
            print(f"  {class_name}: precision={precision:.4f}, recall={recall:.4f}, positives={positives}")
    print(f"Class metrics: {metrics_path}")
    print(f"Wrong predictions: {wrong_path}")


if __name__ == "__main__":
    main()
