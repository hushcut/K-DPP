from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from tqdm import tqdm

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.service.label_analysis import analyze_label_image
from apps.symbol.predict_symbol import DEFAULT_MODEL_PATH, predict_symbol
from apps.text.ocr_text import OcrError

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def image_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise FileNotFoundError(f"이미지 폴더가 없습니다: {folder}")
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def csv_safe(value: Any) -> Any:
    """Prevent spreadsheet formula execution when a CSV is opened."""

    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def flatten_result(
    image_path: Path,
    input_dir: Path,
    parsed: dict[str, Any],
    symbol: dict[str, Any],
    *,
    label_error: str = "",
    symbol_error: str = "",
) -> dict[str, Any]:
    confidence = parsed.get("confidence", {})
    ocr = parsed.get("ocr", {})
    return {
        "file_name": image_path.name,
        "relative_path": image_path.relative_to(input_dir).as_posix(),
        "label_status": parsed.get("status", "failed"),
        "label_error_code": parsed.get("error_code", ""),
        "label_message": parsed.get("message", ""),
        "materials": json.dumps(
            parsed.get("materials", {}),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "materials_korean": parsed.get("materials_korean", ""),
        "selected_part": parsed.get("selected_part", ""),
        "parts": json.dumps(
            parsed.get("parts", {}),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "care_instruction": parsed.get("care_instruction", ""),
        "parser_confidence": confidence.get("parser", ""),
        "ocr_confidence": confidence.get("ocr", ""),
        "ocr_source": ocr.get("source", ""),
        "warnings": json.dumps(
            parsed.get("warnings", []),
            ensure_ascii=False,
        ),
        "raw_ocr_preview": parsed.get("raw_ocr_preview", ""),
        "label_exception": label_error,
        "symbol_status": symbol.get("status", "not_run"),
        "symbols": json.dumps(
            symbol.get("symbols", []),
            ensure_ascii=False,
        ),
        "symbol_exception": symbol_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the AI label pipeline over an image folder."
    )
    parser.add_argument(
        "--split",
        default="valid",
        choices=["train", "valid", "test"],
        help="Used only when --image-dir is omitted.",
    )
    parser.add_argument(
        "--image-dir",
        default="",
        help="Optional image folder. Defaults to data/<split>.",
    )
    parser.add_argument(
        "--credentials",
        default="",
        help=(
            "Google Vision service-account JSON. If omitted, "
            "GOOGLE_APPLICATION_CREDENTIALS is used."
        ),
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--include-symbol-crops",
        action="store_true",
        help=(
            "Also run the symbol classifier. Enable this only when every "
            "input image is an already-cropped single care-symbol image."
        ),
    )
    parser.add_argument(
        "--symbol-model",
        default=str(DEFAULT_MODEL_PATH),
    )
    args = parser.parse_args()

    input_dir = (
        Path(args.image_dir).expanduser().resolve()
        if args.image_dir
        else (DATA_DIR / args.split).resolve()
    )
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else OUTPUT_DIR / f"{args.split}_combined_results.csv"
    )
    paths = image_files(input_dir)
    if not paths:
        raise ValueError(f"처리할 JPG/PNG 이미지가 없습니다: {input_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for image_path in tqdm(paths, desc="AI label analysis"):
        parsed: dict[str, Any] = {
            "status": "failed",
            "error_code": "pipeline_exception",
            "materials": {},
            "parts": {},
        }
        label_error = ""
        try:
            parsed = analyze_label_image(
                image_path,
                credential_path=args.credentials or None,
            )
        except OcrError as exc:
            parsed["error_code"] = type(exc).__name__
            parsed["message"] = str(exc)
            label_error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            # A batch must continue, but unexpected defects stay visible in
            # a dedicated column rather than becoming an ordinary parse miss.
            parsed["message"] = "예상하지 못한 AI 파이프라인 오류"
            label_error = f"{type(exc).__name__}: {exc}"

        symbol: dict[str, Any] = {"status": "not_run", "symbols": []}
        symbol_error = ""
        if args.include_symbol_crops:
            try:
                symbol = predict_symbol(
                    str(image_path),
                    model_path=args.symbol_model,
                )
            except Exception as exc:
                symbol = {"status": "failed", "symbols": []}
                symbol_error = f"{type(exc).__name__}: {exc}"

        rows.append(
            {
                key: csv_safe(value)
                for key, value in flatten_result(
                    image_path,
                    input_dir,
                    parsed,
                    symbol,
                    label_error=label_error,
                    symbol_error=symbol_error,
                ).items()
            }
        )

    fieldnames = list(rows[0])
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    successful = sum(row["label_status"] == "success" for row in rows)
    print(f"Saved: {output_path}")
    print(f"Images: {len(rows)}")
    print(f"Parser success: {successful}/{len(rows)}")
    if not args.include_symbol_crops:
        print(
            "Symbol classification: not run "
            "(full-label photos are outside the classifier input contract)"
        )


if __name__ == "__main__":
    main()
