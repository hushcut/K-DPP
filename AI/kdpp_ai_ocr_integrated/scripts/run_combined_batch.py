from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from apps.service.label_analysis import analyze_label_image
from apps.text.ocr_text import OcrError


BASE_DIR = Path(__file__).resolve().parents[1]
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
    *,
    label_error: str = "",
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
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the AI label pipeline over an image folder."
    )
    parser.add_argument(
        "--image-dir",
        required=True,
        help="OCR로 분석할 라벨 이미지 폴더.",
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
    args = parser.parse_args()

    input_dir = Path(args.image_dir).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else OUTPUT_DIR / "label_batch_results.csv"
    )
    paths = image_files(input_dir)
    if not paths:
        raise ValueError(f"처리할 JPG/PNG 이미지가 없습니다: {input_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for image_path in paths:
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

        rows.append(
            {
                key: csv_safe(value)
                for key, value in flatten_result(
                    image_path,
                    input_dir,
                    parsed,
                    label_error=label_error,
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

if __name__ == "__main__":
    main()
