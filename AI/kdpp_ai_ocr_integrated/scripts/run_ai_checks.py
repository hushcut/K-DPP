from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


def run_check(label: str, command: list[str]) -> None:
    print(f"\n[{label}]", flush=True)
    completed = subprocess.run(
        command,
        cwd=BASE_DIR,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI 문법·회귀 테스트·OCR QA 정답지 검사를 실행합니다."
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument(
        "--qa-image-dir",
        help="OCR QA 이미지 폴더. --qa-answer-key와 함께 지정해야 합니다.",
    )
    parser.add_argument(
        "--qa-answer-key",
        help="OCR QA 정답 CSV. --qa-image-dir와 함께 지정해야 합니다.",
    )
    args = parser.parse_args()

    run_check("Syntax check", [sys.executable, "-B", "-m", "scripts.check_python_syntax"])
    if args.skip_tests:
        print("[Regression tests] SKIP: --skip-tests was requested.")
    else:
        run_check("Regression tests", [sys.executable, "-m", "pytest"])

    if bool(args.qa_image_dir) != bool(args.qa_answer_key):
        raise SystemExit(
            "--qa-image-dir와 --qa-answer-key는 함께 지정해야 합니다."
        )
    if args.qa_image_dir and args.qa_answer_key:
        run_check(
            "OCR QA dataset audit",
            [
                sys.executable,
                "-m",
                "scripts.audit_ocr_qa_dataset",
                "--image-dir",
                args.qa_image_dir,
                "--answer-key",
                args.qa_answer_key,
                "--strict",
            ],
        )

if __name__ == "__main__":
    main()
