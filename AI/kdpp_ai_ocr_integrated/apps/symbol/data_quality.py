from __future__ import annotations

import csv
import hashlib
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LeakageGroup:
    kind: str
    key: str
    examples: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SplitAudit:
    """A read-only summary of one labelled image split."""

    split: str
    sample_count: int
    all_negative_count: int
    multi_positive_count: int
    label_cardinality: dict[int, int]
    positive_count_by_class: dict[str, int]
    missing_positive_classes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "split": self.split,
            "sample_count": self.sample_count,
            "all_negative_count": self.all_negative_count,
            "multi_positive_count": self.multi_positive_count,
            "label_cardinality": dict(self.label_cardinality),
            "positive_count_by_class": dict(self.positive_count_by_class),
            "missing_positive_classes": list(self.missing_positive_classes),
        }


@dataclass(frozen=True)
class DatasetAudit:
    """Dataset contract information needed before model training starts."""

    class_names: tuple[str, ...]
    task_type: str
    splits: tuple[SplitAudit, ...]

    def to_dict(self) -> dict:
        total_samples = sum(split.sample_count for split in self.splits)
        return {
            "class_names": list(self.class_names),
            "task_type": self.task_type,
            "total_samples": total_samples,
            "splits": [split.to_dict() for split in self.splits],
            "split_ratios": {
                split.split: round(split.sample_count / total_samples, 4)
                if total_samples
                else 0.0
                for split in self.splits
            },
        }


def normalize_origin_name(filename: str) -> str:
    name = Path(filename).stem.casefold()
    name = re.sub(r"_(?:jpg|jpeg|png)\.rf\.[a-f0-9]+$", "", name)
    name = re.sub(r"\.rf\.[a-f0-9]+$", "", name)
    return name


def read_split_filenames(data_dir: str | os.PathLike[str], split: str) -> list[str]:
    split_dir = Path(data_dir) / split
    csv_path = split_dir / "_classes.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"분할 CSV가 없습니다: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        try:
            raw_header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"분할 CSV가 비어 있습니다: {csv_path}") from exc
        header = [value.strip() for value in raw_header]
        if "filename" not in header:
            raise ValueError(f"filename 컬럼이 없습니다: {csv_path}")
        filename_index = header.index("filename")

        filenames = []
        for row_number, row in enumerate(reader, start=2):
            if filename_index >= len(row):
                raise ValueError(
                    f"{csv_path} {row_number}행에 filename 값이 없습니다."
                )
            filename = row[filename_index].strip()
            if filename:
                filenames.append(filename)

    if not filenames:
        raise ValueError(f"분할에 이미지 행이 없습니다: {csv_path}")
    return filenames


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_split_leakage(
    data_dir: str | os.PathLike[str],
    splits: tuple[str, ...] = ("train", "valid", "test"),
) -> list[LeakageGroup]:
    data_path = Path(data_dir)
    origin_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    hash_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for split in splits:
        split_dir = data_path / split
        for filename in read_split_filenames(data_path, split):
            origin_groups[normalize_origin_name(filename)].append((split, filename))
            image_path = split_dir / filename
            if not image_path.is_file():
                raise FileNotFoundError(
                    f"CSV에는 있지만 이미지가 없습니다: {image_path}"
                )
            hash_groups[_sha256(image_path)].append((split, filename))

    leaks: list[LeakageGroup] = []
    for kind, groups in (("origin_name", origin_groups), ("sha256", hash_groups)):
        for key, examples in groups.items():
            if len({split for split, _ in examples}) > 1:
                leaks.append(
                    LeakageGroup(
                        kind=kind,
                        key=key,
                        examples=tuple(examples),
                    )
                )
    return sorted(leaks, key=lambda item: (item.kind, item.key))


def assert_no_split_leakage(
    data_dir: str | os.PathLike[str],
    splits: tuple[str, ...] = ("train", "valid", "test"),
) -> None:
    leaks = find_split_leakage(data_dir, splits)
    if not leaks:
        return

    examples = []
    for leak in leaks[:10]:
        locations = "; ".join(
            f"{split}/{filename}" for split, filename in leak.examples[:4]
        )
        examples.append(f"{leak.kind}:{leak.key} -> {locations}")
    raise ValueError(
        f"train/valid/test 데이터 누수 {len(leaks)}개를 발견했습니다.\n"
        + "\n".join(examples)
    )


def audit_dataset(
    data_dir: str | os.PathLike[str],
    splits: tuple[str, ...] = ("train", "valid", "test"),
) -> DatasetAudit:
    """Read dataset metadata and labels without loading image pixels.

    The report makes the current label semantics visible before training:
    a positive-label cardinality above one means the CSV is multi-label.
    """

    # Import locally to keep the dataset reader independent from this module.
    from apps.symbol.dataset_csv import SymbolCsvDataset

    audits: list[SplitAudit] = []
    expected_class_names: tuple[str, ...] | None = None
    has_any_positive = False
    has_multi_positive = False

    for split in splits:
        dataset = SymbolCsvDataset(str(Path(data_dir) / split))
        class_names = tuple(dataset.class_names)
        if expected_class_names is None:
            expected_class_names = class_names
        elif class_names != expected_class_names:
            raise ValueError(
                f"클래스 컬럼 또는 순서가 다릅니다: "
                f"{splits[0]}/{split} _classes.csv를 확인하세요."
            )

        cardinalities = Counter(
            int(sum(labels)) for _, labels in dataset.samples
        )
        class_counts = dataset.class_counts()
        positive_count_by_class = {
            class_name: int(class_counts.get(index, 0))
            for index, class_name in enumerate(class_names)
        }
        missing_positive_classes = tuple(
            class_name
            for class_name, count in positive_count_by_class.items()
            if count == 0
        )
        has_any_positive = has_any_positive or any(
            count > 0 for count in positive_count_by_class.values()
        )
        has_multi_positive = has_multi_positive or any(
            count > 0 for cardinality, count in cardinalities.items()
            if cardinality > 1
        )
        audits.append(
            SplitAudit(
                split=split,
                sample_count=len(dataset),
                all_negative_count=dataset.audit.all_negative_rows,
                multi_positive_count=sum(
                    count
                    for cardinality, count in cardinalities.items()
                    if cardinality > 1
                ),
                label_cardinality=dict(sorted(cardinalities.items())),
                positive_count_by_class=positive_count_by_class,
                missing_positive_classes=missing_positive_classes,
            )
        )

    if expected_class_names is None:
        raise ValueError("감사할 데이터 분할이 없습니다.")
    task_type = (
        "multi_label"
        if has_multi_positive
        else "single_label_with_background"
        if has_any_positive
        else "all_negative"
    )
    return DatasetAudit(
        class_names=expected_class_names,
        task_type=task_type,
        splits=tuple(audits),
    )


def assert_train_class_coverage(dataset_audit: DatasetAudit) -> None:
    """Reject training data that declares classes with no positive example."""

    train_audit = next(
        (split for split in dataset_audit.splits if split.split == "train"),
        None,
    )
    if train_audit is None:
        raise ValueError("학습 데이터(train) 감사 결과가 없습니다.")
    if not train_audit.missing_positive_classes:
        return
    raise ValueError(
        "학습 데이터에 양성 샘플이 없는 클래스가 있습니다: "
        + ", ".join(train_audit.missing_positive_classes)
    )
