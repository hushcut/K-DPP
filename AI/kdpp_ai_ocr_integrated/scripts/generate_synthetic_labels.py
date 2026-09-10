import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.synthetic.label_generator import generate_dataset, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a deterministic synthetic material-label dataset.")
    parser.add_argument(
        "--config",
        default=str(BASE_DIR / "configs" / "synthetic_labels_v1.json"),
        help="Generation config JSON path.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output directory override. The directory must be empty.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    summary = generate_dataset(config, args.output or None)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
