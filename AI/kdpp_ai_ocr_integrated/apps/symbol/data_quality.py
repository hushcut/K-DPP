from __future__ import annotations

import csv
import hashlib
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LeakageGroup:
    kind: str
    key: str
    examples: tuple[tuple[str, str], ...]


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
