import os

import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms

from apps.symbol.class_map import CLASS_TO_KO

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_MODEL_PATH = os.path.join(BASE_DIR, "models", "symbol", "best_symbol_model_exp.pt")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
IMG_SIZE = 224


def load_model(model_path: str = DEFAULT_MODEL_PATH):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"모델 파일이 없습니다: {model_path}")

    checkpoint = torch.load(model_path, map_location=DEVICE)
    class_names = checkpoint["class_names"]

    model = models.resnet18(weights=None)
    state_dict = checkpoint["model_state_dict"]
    if "fc.1.weight" in state_dict:
        model.fc = nn.Sequential(
            nn.Dropout(p=0.3),
            nn.Linear(model.fc.in_features, len(class_names)),
        )
    else:
        model.fc = nn.Linear(model.fc.in_features, len(class_names))
    model.load_state_dict(state_dict)
    model = model.to(DEVICE)
    model.eval()
    return model, class_names


def predict_symbol(image_path: str, model_path: str = DEFAULT_MODEL_PATH) -> dict:
    model, class_names = load_model(model_path)

    transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    image = Image.open(image_path).convert("RGB")
    x = transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        probs = torch.sigmoid(model(x))[0]

    selected = []
    for idx, prob in enumerate(probs):
        confidence = float(prob)
        if confidence >= 0.5:
            class_en = class_names[idx]
            selected.append({
                "symbol_class": class_en,
                "symbol_korean": CLASS_TO_KO.get(class_en, class_en),
                "symbol_confidence": round(confidence, 4),
            })

    if not selected:
        pred_idx = int(probs.argmax().item())
        class_en = class_names[pred_idx]
        selected.append({
            "symbol_class": class_en,
            "symbol_korean": CLASS_TO_KO.get(class_en, class_en),
            "symbol_confidence": round(float(probs[pred_idx]), 4),
        })

    return {
        "symbols": selected,
        "symbol_class": "; ".join(item["symbol_class"] for item in selected),
        "symbol_korean": "; ".join(item["symbol_korean"] for item in selected),
        "symbol_confidence": max(item["symbol_confidence"] for item in selected),
    }
