from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.text.qa_dataset import (
    answer_key_columns,
    audit_qa_answer_key,
    load_qa_answer_key,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def image_names(image_dir: Path) -> set[str]:
    if not image_dir.is_dir():
        raise FileNotFoundError(f"이미지 폴더가 없습니다: {image_dir}")
    return {
        path.name
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "OCR 소재 분석 QA 정답지의 라벨 구조, 조건 메타데이터, "
            "split/source-group 누수를 읽기 전용으로 점검합니다."
        )
    )
    parser.add_argument("--answer-key", required=True)
    parser.add_argument(
        "--image-dir",
        help="선택 사항. 지정하면 이미지와 정답지의 1:1 대응도 검사합니다.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="이미지/정답 불일치 또는 source_group split 누수를 오류로 처리합니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    answer_key_path = Path(args.answer_key).expanduser().resolve()
    answers = load_qa_answer_key(answer_key_path)
    report = audit_qa_answer_key(
        answers,
        columns=answer_key_columns(answer_key_path),
    ).to_dict()

    missing_answers: list[str] = []
    missing_images: list[str] = []
    if args.image_dir:
        available_images = image_names(Path(args.image_dir).expanduser().resolve())
        expected_images = set(answers)
        missing_answers = sorted(available_images - expected_images)
        missing_images = sorted(expected_images - available_images)
        report["image_count"] = len(available_images)
        report["images_without_answers"] = missing_answers
        report["answers_without_images"] = missing_images

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and (
        missing_answers
        or missing_images
        or report["source_group_split_leaks"]
    ):
        raise SystemExit("QA dataset integrity check failed.")


if __name__ == "__main__":
    main()
