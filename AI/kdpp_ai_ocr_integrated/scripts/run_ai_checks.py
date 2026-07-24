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
    args = parser.parse_args()

    run_check(
        "Python compile",
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "apps",
            "scripts",
            "tests",
        ],
    )
    run_check("Regression tests", [sys.executable, "-m", "pytest"])

    if args.skip_leakage:
        print(
            "\n[Split leakage]\nSKIP: --skip-leakage was supplied.",
            flush=True,
        )
        return

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

    run_check(
        "Split leakage",
        [
            sys.executable,
            "scripts/check_split_leakage.py",
            "--data-dir",
            str(data_dir),
            "--splits",
            *splits,
        ],
    )


if __name__ == "__main__":
    main()
