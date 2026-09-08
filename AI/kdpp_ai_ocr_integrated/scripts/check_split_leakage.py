from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE_DIR / "data"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.symbol.data_quality import find_split_leakage


def main() -> None:
    parser = argparse.ArgumentParser(
        description="원본 파일명과 SHA-256을 이용한 split 누수 검사"
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "valid", "test"],
    )
    args = parser.parse_args()

    leaks = find_split_leakage(
        Path(args.data_dir).expanduser().resolve(),
        tuple(args.splits),
    )
    if not leaks:
        print("PASS: split 간 원본명/SHA-256 누수가 없습니다.")
        return

    print(f"FAIL: split 누수 그룹 {len(leaks)}개")
    for leak in leaks[:50]:
        examples = "; ".join(
            f"{split}/{filename}" for split, filename in leak.examples[:6]
        )
        print(f"- {leak.kind}:{leak.key} -> {examples}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
