from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.symbol.data_quality import audit_dataset, assert_no_split_leakage


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE_DIR / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "세탁기호 데이터셋의 라벨 구조, 분할 비율, 클래스 표본 수를 "
            "읽기 전용으로 점검합니다."
        )
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "valid", "test"],
    )
    parser.add_argument(
        "--skip-leakage",
        action="store_true",
        help="원본명/SHA-256 기반 split 누수 검사를 건너뜁니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    splits = tuple(args.splits)
    if not args.skip_leakage:
        assert_no_split_leakage(data_dir, splits)

    report = audit_dataset(data_dir, splits)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
