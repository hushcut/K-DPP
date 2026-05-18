import os
from collections import Counter

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import models, transforms

from apps.symbol.dataset_csv import SymbolCsvDataset

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
TRAIN_DIR = os.path.join(DATA_DIR, "train")
VALID_DIR = os.path.join(DATA_DIR, "valid")
MODEL_DIR = os.path.join(BASE_DIR, "models", "symbol")
MODEL_PATH = os.path.join(MODEL_DIR, "best_symbol_model_exp.pt")

BATCH_SIZE = 16
EPOCHS = 12
PATIENCE = 4
LR = 1e-4
WEIGHT_DECAY = 1e-4
IMG_SIZE = 224
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def build_transforms():
    train_tfms = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.RandomResizedCrop(IMG_SIZE, scale=(0.75, 1.0), ratio=(0.85, 1.15)),
        transforms.RandomApply([transforms.RandomRotation(8)], p=0.7),
        transforms.RandomApply([transforms.ColorJitter(brightness=0.25, contrast=0.25)], p=0.7),
        transforms.RandomApply([transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 1.2))], p=0.25),
        transforms.RandomGrayscale(p=0.15),
        transforms.ToTensor(),
        transforms.RandomErasing(p=0.15, scale=(0.02, 0.08), ratio=(0.3, 3.3)),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    eval_tfms = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    return train_tfms, eval_tfms


def compute_pos_weights(class_counts: Counter, num_classes: int, num_samples: int) -> torch.Tensor:
    weights = []
    for class_idx in range(num_classes):
        count = max(class_counts.get(class_idx, 0), 1)
        weights.append(max((num_samples - count) / count, 1.0))
    return torch.tensor(weights, dtype=torch.float32).to(DEVICE)


def run_epoch(model, loader, criterion, optimizer=None):
    is_train = optimizer is not None
    model.train() if is_train else model.eval()

    loss_sum = 0.0
    correct = 0
    total = 0

    context = torch.enable_grad() if is_train else torch.no_grad()
    with context:
        for images, labels, _ in loader:
            images = images.to(DEVICE)
            labels = labels.to(DEVICE)

            if is_train:
                optimizer.zero_grad()

            outputs = model(images)
            loss = criterion(outputs, labels)

            if is_train:
                loss.backward()
                optimizer.step()

            loss_sum += loss.item() * images.size(0)
            preds = (torch.sigmoid(outputs) >= 0.5).float()
            correct += (preds == labels).all(dim=1).sum().item()
            total += labels.size(0)

    return loss_sum / total, correct / total


def main():
    train_tfms, valid_tfms = build_transforms()
    train_ds = SymbolCsvDataset(TRAIN_DIR, transform=train_tfms)
    valid_ds = SymbolCsvDataset(VALID_DIR, transform=valid_tfms)

    if train_ds.class_names != valid_ds.class_names:
        raise ValueError("train/valid 클래스 컬럼 순서가 다릅니다. _classes.csv를 확인하세요.")

    class_names = train_ds.class_names
    class_counts = train_ds.class_counts()

    print(f"DEVICE: {DEVICE}")
    print(f"Train samples: {len(train_ds)}")
    print(f"Valid samples: {len(valid_ds)}")
    print("[Class counts]")
    for idx, name in enumerate(class_names):
        print(f"  {name}: {class_counts.get(idx, 0)}")

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    valid_loader = DataLoader(valid_ds, batch_size=BATCH_SIZE, shuffle=False)

    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.fc = nn.Sequential(
        nn.Dropout(p=0.3),
        nn.Linear(model.fc.in_features, len(class_names)),
    )
    model = model.to(DEVICE)

    criterion = nn.BCEWithLogitsLoss(
        pos_weight=compute_pos_weights(class_counts, len(class_names), len(train_ds)),
    )
    optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

    os.makedirs(MODEL_DIR, exist_ok=True)
    best_val_acc = 0.0
    best_val_loss = float("inf")
    epochs_without_improvement = 0

    for epoch in range(1, EPOCHS + 1):
        train_loss, train_acc = run_epoch(model, train_loader, criterion, optimizer)
        valid_loss, valid_acc = run_epoch(model, valid_loader, criterion)

        print(
            f"Epoch {epoch:02d}/{EPOCHS} | "
            f"train_loss={train_loss:.4f}, train_acc={train_acc:.4f} | "
            f"valid_loss={valid_loss:.4f}, valid_acc={valid_acc:.4f}"
        )

        improved = valid_acc > best_val_acc or (
            valid_acc == best_val_acc and valid_loss < best_val_loss
        )
        if improved:
            best_val_acc = valid_acc
            best_val_loss = valid_loss
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "class_names": class_names,
                    "best_val_exact_match": best_val_acc,
                    "best_val_loss": best_val_loss,
                    "config": {
                        "img_size": IMG_SIZE,
                        "batch_size": BATCH_SIZE,
                        "lr": LR,
                        "weight_decay": WEIGHT_DECAY,
                        "task": "multi_label",
                        "threshold": 0.5,
                    },
                },
                MODEL_PATH,
            )
            print(f"  saved: {MODEL_PATH}")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= PATIENCE:
                print(f"Early stopping: {PATIENCE} epochs without valid improvement.")
                break

    print(f"Best valid exact-match accuracy: {best_val_acc:.4f}")


if __name__ == "__main__":
    main()
