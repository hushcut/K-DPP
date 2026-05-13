import argparse
import csv
import os

from tqdm import tqdm

from apps.symbol.predict_symbol import predict_symbol
from apps.text.ocr_text import run_ocr
from apps.text.parse_label import parse_label

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
DEFAULT_MODEL = os.path.join(BASE_DIR, "models", "symbol", "best_symbol_model_exp.pt")


def image_files(folder: str):
    for root, _, files in os.walk(folder):
        for file in files:
            if file.lower().endswith((".jpg", ".jpeg", ".png")):
                yield os.path.join(root, file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="valid", choices=["train", "valid", "test"])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--credentials", default="key.json")
    args = parser.parse_args()

    split_dir = os.path.join(DATA_DIR, args.split)
    paths = list(image_files(split_dir))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"{args.split}_combined_results.csv")

    rows = []
    for image_path in tqdm(paths, desc=f"combined {args.split}"):
        try:
            symbol = predict_symbol(image_path, args.model)
        except Exception as exc:
            symbol = {
                "symbol_class": "",
                "symbol_korean": "",
                "symbol_confidence": 0,
                "symbol_error": str(exc),
            }

        try:
            raw_text = run_ocr(image_path, args.credentials)
            parsed = parse_label(raw_text)
        except Exception as exc:
            parsed = {
                "materials_korean": "",
                "care_text": "",
                "raw_ocr_preview": "",
                "ocr_error": str(exc),
            }

        rows.append({
            "image_path": image_path,
            "symbol_class": symbol.get("symbol_class", ""),
            "symbol_korean": symbol.get("symbol_korean", ""),
            "symbol_confidence": symbol.get("symbol_confidence", 0),
            "symbol_error": symbol.get("symbol_error", ""),
            "materials_korean": parsed.get("materials_korean", ""),
            "care_text": parsed.get("care_text", ""),
            "raw_ocr_preview": parsed.get("raw_ocr_preview", ""),
            "ocr_error": parsed.get("ocr_error", ""),
        })

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = [
            "image_path",
            "symbol_class",
            "symbol_korean",
            "symbol_confidence",
            "symbol_error",
            "materials_korean",
            "care_text",
            "raw_ocr_preview",
            "ocr_error",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()

