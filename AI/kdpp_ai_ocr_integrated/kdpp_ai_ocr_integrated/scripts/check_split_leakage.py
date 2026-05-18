import argparse
import csv
import os
import re
from collections import defaultdict

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")


def normalize_origin_name(filename: str) -> str:
    name = os.path.splitext(os.path.basename(filename))[0].lower()
    name = re.sub(r"_jpg\.rf\.[a-f0-9]+$", "", name)
    name = re.sub(r"_png\.rf\.[a-f0-9]+$", "", name)
    name = re.sub(r"_jpeg\.rf\.[a-f0-9]+$", "", name)
    name = re.sub(r"\.rf\.[a-f0-9]+$", "", name)
    return name


def read_filenames(split: str) -> set[str]:
    csv_path = os.path.join(DATA_DIR, split, "_classes.csv")
    if not os.path.exists(csv_path):
        return set()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return {row["filename"] for row in reader if row.get("filename")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", nargs="+", default=["train", "valid", "test"])
    args = parser.parse_args()

    origins = defaultdict(list)
    for split in args.splits:
        for filename in read_filenames(split):
            origins[normalize_origin_name(filename)].append((split, filename))

    leaks = {
        origin: rows
        for origin, rows in origins.items()
        if len({split for split, _ in rows}) > 1
    }

    if not leaks:
        print("No likely Roboflow-origin leakage found across splits.")
        return

    print(f"Potential split leakage groups: {len(leaks)}")
    for origin, rows in sorted(leaks.items())[:50]:
        split_names = ", ".join(sorted({split for split, _ in rows}))
        examples = "; ".join(f"{split}/{filename}" for split, filename in rows[:4])
        print(f"- {origin} [{split_names}] {examples}")


if __name__ == "__main__":
    main()

