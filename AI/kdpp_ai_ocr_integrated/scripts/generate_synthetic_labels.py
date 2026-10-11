"""Generate deterministic synthetic multilingual material-label images."""

from __future__ import annotations

import argparse
from pathlib import Path

from apps.synthetic.label_generator import generate_dataset, load_config


BASE_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(BASE_DIR / "configs" / "synthetic_labels_v1.json"),
    )
    parser.add_argument(
        "--output",
        default=str(BASE_DIR / "outputs" / "synthetic" / "synthetic_labels_v1"),
    )
    args = parser.parse_args()
    summary = generate_dataset(load_config(args.config), args.output)
    print(f"Generated {summary['image_count']} images: {summary['output_dir']}")


if __name__ == "__main__":
    main()
