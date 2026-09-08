import csv
from pathlib import Path

import pytest
from PIL import Image

from apps.symbol.data_quality import (
    assert_train_class_coverage,
    audit_dataset,
    find_split_leakage,
)
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


def test_dataset_audit_reports_multilabel_distribution(tmp_path: Path) -> None:
    train = tmp_path / "train"
    valid = tmp_path / "valid"
    write_classes_csv(
        train,
        [("one.png", 1, 0), ("two.png", 1, 1)],
    )
    write_classes_csv(valid, [("three.png", 0, 1)])
    for split, names in ((train, ("one.png", "two.png")), (valid, ("three.png",))):
        for name in names:
            write_png(split / name)

    report = audit_dataset(tmp_path, ("train", "valid"))

    assert report.task_type == "multi_label"
    assert report.splits[0].label_cardinality == {1: 1, 2: 1}
    assert report.to_dict()["split_ratios"] == {"train": 0.6667, "valid": 0.3333}


def test_train_class_coverage_rejects_unlearnable_class(tmp_path: Path) -> None:
    train = tmp_path / "train"
    valid = tmp_path / "valid"
    write_classes_csv(train, [("train.png", 1, 0)])
    write_classes_csv(valid, [("valid.png", 0, 1)])
    write_png(train / "train.png")
    write_png(valid / "valid.png")

    report = audit_dataset(tmp_path, ("train", "valid"))

    with pytest.raises(ValueError, match="iron"):
        assert_train_class_coverage(report)

