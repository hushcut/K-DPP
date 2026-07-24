import csv
from pathlib import Path

import pytest
from PIL import Image

from apps.symbol.data_quality import find_split_leakage
from apps.symbol.dataset_csv import SymbolCsvDataset


def write_png(path: Path, color: str = "white") -> None:
    Image.new("RGB", (16, 16), color).save(path)


def write_classes_csv(
    folder: Path,
    rows: list[tuple[str, int, int]],
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "_classes.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["filename", "wash", "iron"])
        writer.writerows(rows)


def test_dataset_keeps_all_negative_examples(tmp_path: Path) -> None:
    split = tmp_path / "train"
    write_classes_csv(split, [("none.png", 0, 0)])
    write_png(split / "none.png")

    dataset = SymbolCsvDataset(str(split))

    assert len(dataset) == 1
    assert dataset.audit.all_negative_rows == 1
    _, labels, _ = dataset[0]
    assert labels.tolist() == [0.0, 0.0]


def test_dataset_fails_when_csv_image_is_missing(tmp_path: Path) -> None:
    split = tmp_path / "train"
    write_classes_csv(split, [("missing.png", 1, 0)])

    with pytest.raises(FileNotFoundError):
        SymbolCsvDataset(str(split))


def test_leakage_finder_detects_origin_and_identical_bytes(tmp_path: Path) -> None:
    files = {
        "train": "shirt_jpg.rf.aaaa.png",
        "valid": "shirt_jpg.rf.bbbb.png",
        "test": "other_jpg.rf.cccc.png",
    }
    for split_name, filename in files.items():
        split = tmp_path / split_name
        write_classes_csv(split, [(filename, 1, 0)])
        write_png(
            split / filename,
            color="white" if split_name != "test" else "black",
        )

    leaks = find_split_leakage(tmp_path)

    assert {leak.kind for leak in leaks} == {"origin_name", "sha256"}

