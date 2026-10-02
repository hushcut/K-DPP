"""Evaluate a synthetic label manifest with the parser only; no OCR API call is made."""

from __future__ import annotations

import argparse
from pathlib import Path

from apps.synthetic.evaluation import evaluate_manifest, write_evaluation


BASE_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=str(BASE_DIR / "outputs" / "synthetic" / "synthetic_labels_v1" / "manifest.csv"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(BASE_DIR / "outputs" / "synthetic" / "synthetic_labels_v1" / "evaluation"),
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="Allowed percentage-point error for exact composition.",
    )
    args = parser.parse_args()
    results, group_results, summary = evaluate_manifest(
        args.manifest,
        tolerance=args.tolerance,
    )
    output_dir = write_evaluation(args.output_dir, results, group_results, summary)
    print(
        "Synthetic parser-only accuracy: "
        f"{summary['image_exact_composition_accuracy'] * 100:.1f}% "
        f"({summary['image_exact_composition_count']}/{summary['image_count']})"
    )
    print(f"Synthetic evaluation: {output_dir}")


if __name__ == "__main__":
    main()
