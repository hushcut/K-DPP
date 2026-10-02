from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE_DIR / "data"


def run_check(label: str, command: list[str]) -> None:
    print(f"\n[{label}]", flush=True)
    completed = subprocess.run(
        command,
        cwd=BASE_DIR,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def available_splits(data_dir: Path) -> list[str]:
    return [
        split
        for split in ("train", "valid", "test")
        if (data_dir / split / "_classes.csv").is_file()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run compile, regression, and data-leakage checks for AI only."
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--skip-leakage", action="store_true")
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
    data_dir = Path(args.data_dir).expanduser().resolve()
    splits = available_splits(data_dir)
    if not splits:
        print(
            "\n[Split leakage]\n"
            f"SKIP: no _classes.csv files were found under {data_dir}.",
            flush=True,
        )
        return
    if "train" not in splits or "valid" not in splits:
        raise SystemExit(
            "Dataset is incomplete: train and valid _classes.csv are required."
        )

    dataset_audit_command = [
        sys.executable,
        "-m",
        "scripts.audit_symbol_dataset",
        "--data-dir",
        str(data_dir),
        "--splits",
        *splits,
    ]
    if args.skip_leakage:
        dataset_audit_command.append("--skip-leakage")
    run_check("Dataset audit", dataset_audit_command)


if __name__ == "__main__":
    main()
