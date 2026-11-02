from __future__ import annotations

import ast
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORIES = ("apps", "scripts", "tests")
QA_DIRECTORY = BASE_DIR.parents[1] / "QA"


def python_files() -> list[Path]:
    files = [
        path
        for directory in SOURCE_DIRECTORIES
        for path in (BASE_DIR / directory).rglob("*.py")
    ]
    if QA_DIRECTORY.is_dir():
        files.extend(QA_DIRECTORY.rglob("*.py"))
    return files


def main() -> None:
    files = python_files()
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"PASS: {len(files)} Python files passed syntax validation.")


if __name__ == "__main__":
    main()
