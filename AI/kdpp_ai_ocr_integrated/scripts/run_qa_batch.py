import argparse
import csv
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.text.ocr_text import run_ocr
from apps.text.parse_label import parse_label

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_answer_materials(row: dict) -> dict[str, float]:
    direct = (row.get("answer_materials") or "").strip()
    if ":" in direct:
        result = {}
        for item in direct.split(";"):
            item = item.strip()
            if not item or ":" not in item:
                continue
            key, value = item.split(":", 1)
            try:
                result[key.strip()] = float(value.strip())
            except ValueError:
                continue
        return result

    materials = [item.strip() for item in direct.split(";") if item.strip()]
    ratios = [item.strip() for item in (row.get("answer_ratios") or "").split(";") if item.strip()]
    result = {}
    for material, ratio in zip(materials, ratios):
        try:
            result[material] = float(ratio)
        except ValueError:
            continue
    return result


def normalize_values(values: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 1) for key, value in values.items() if value is not None}


def compare_materials(answer: dict[str, float], predicted: dict[str, float], tolerance: float) -> tuple[str, str]:
    answer = normalize_values(answer)
    predicted = normalize_values(predicted)

    if not predicted:
        return "failed", "no_predicted_materials"

    missing = sorted(set(answer) - set(predicted))
    extra = sorted(set(predicted) - set(answer))
    diffs = []
    for key in sorted(set(answer) & set(predicted)):
        diff = predicted[key] - answer[key]
        if abs(diff) > tolerance:
            diffs.append(f"{key}:{diff:+.1f}")

    if missing or extra or diffs:
        reasons = []
        if missing:
            reasons.append("missing=" + ";".join(missing))
        if extra:
            reasons.append("extra=" + ";".join(extra))
        if diffs:
            reasons.append("ratio_diff=" + ";".join(diffs))
        return "failed", " | ".join(reasons)

    return "success", ""


def load_answer_key(path: Path) -> dict[str, dict]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return {row.get("file_name", "").strip(): row for row in reader if row.get("file_name")}


def image_files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run K-DPP OCR material QA batch.")
    parser.add_argument("--image-dir", required=True, help="Folder containing QA images.")
    parser.add_argument("--answer-key", default="", help="Optional answer key CSV.")
    parser.add_argument("--credentials", default="key.json", help="Google Vision service account key path.")
    parser.add_argument("--output", default=str(BASE_DIR / "outputs" / "qa_batch_results.csv"))
    parser.add_argument("--tolerance", type=float, default=3.0, help="Allowed percentage point error.")
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    answers = load_answer_key(Path(args.answer_key)) if args.answer_key else {}
    rows = []

    for image_path in image_files(image_dir):
        row = {
            "file_name": image_path.name,
            "status": "failed",
            "judgment": "not_compared",
            "failure_reason": "",
            "answer_materials": "",
            "predicted_materials": "",
            "materials_korean": "",
            "selected_part": "",
            "raw_ocr_preview": "",
            "error": "",
        }
        answer_row = answers.get(image_path.name, {})
        answer_materials = parse_answer_materials(answer_row) if answer_row else {}
        row["answer_materials"] = json.dumps(answer_materials, ensure_ascii=False, sort_keys=True)

        try:
            text = run_ocr(str(image_path), args.credentials)
            parsed = parse_label(text)
            row["status"] = parsed.get("status", "failed")
            row["predicted_materials"] = json.dumps(parsed.get("materials", {}), ensure_ascii=False, sort_keys=True)
            row["materials_korean"] = parsed.get("materials_korean", "")
            row["selected_part"] = parsed.get("selected_part", "")
            row["raw_ocr_preview"] = parsed.get("raw_ocr_preview", "")

            if answer_materials:
                judgment, reason = compare_materials(answer_materials, parsed.get("materials", {}), args.tolerance)
                row["judgment"] = judgment
                row["failure_reason"] = reason
        except Exception as exc:
            row["error"] = str(exc)
            row["failure_reason"] = "exception"

        rows.append(row)

    fieldnames = [
        "file_name", "status", "judgment", "failure_reason", "answer_materials",
        "predicted_materials", "materials_korean", "selected_part", "raw_ocr_preview", "error",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    compared = [row for row in rows if row["judgment"] in {"success", "failed"}]
    success = sum(1 for row in compared if row["judgment"] == "success")
    print(f"Saved: {output_path}")
    print(f"Images: {len(rows)}")
    if compared:
        print(f"Compared: {len(compared)}")
        print(f"Success: {success}")
        print(f"Accuracy: {success / len(compared) * 100:.1f}%")


if __name__ == "__main__":
    main()
