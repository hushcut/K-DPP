from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import torch
from torch.utils.data import Dataset


@dataclass(frozen=True)
class DatasetAudit:
    csv_rows: int
    loaded_rows: int
    all_negative_rows: int
    missing_files: tuple[str, ...]


def _parse_binary_label(
    raw_value: str,
    *,
    csv_path: Path,
    row_number: int,
    class_name: str,
) -> float:
    value = raw_value.strip()
    if value in {"", "0", "0.0"}:
        return 0.0
    if value in {"1", "1.0"}:
        return 1.0
    raise ValueError(
        f"{csv_path} {row_number}행 {class_name} 값이 0/1이 아닙니다: {raw_value!r}"
    )


class SymbolCsvDataset(Dataset):
    def __init__(
        self,
        folder_path: str,
        transform=None,
        *,
        strict_missing: bool = True,
    ):
        self.folder_path = Path(folder_path)
        self.csv_path = self.folder_path / "_classes.csv"
        self.transform = transform

        if not self.csv_path.is_file():
            raise FileNotFoundError(
                f"_classes.csv 파일이 없습니다: {self.csv_path}"
            )

        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            try:
                raw_header = next(reader)
            except StopIteration as exc:
                raise ValueError(f"CSV 파일이 비어 있습니다: {self.csv_path}") from exc

            header = [value.strip() for value in raw_header]
            if len(set(header)) != len(header):
                raise ValueError(
                    f"공백 제거 후 중복된 CSV 컬럼이 있습니다: {self.csv_path}"
                )
            if "filename" not in header:
                raise ValueError("CSV에 'filename' 컬럼이 없습니다.")

            filename_index = header.index("filename")
            self.class_names = [
                value for index, value in enumerate(header) if index != filename_index
            ]
            if not self.class_names:
                raise ValueError("CSV에 심볼 클래스 컬럼이 없습니다.")

            self.samples: list[tuple[str, list[float]]] = []
            missing_files: list[str] = []
            all_negative_rows = 0
            csv_rows = 0
            seen_filenames: set[str] = set()

            for row_number, row in enumerate(reader, start=2):
                if not any(value.strip() for value in row):
                    continue
                csv_rows += 1
                if len(row) != len(header):
                    raise ValueError(
                        f"{self.csv_path} {row_number}행 컬럼 수가 헤더와 다릅니다."
                    )

                filename = row[filename_index].strip()
                if not filename:
                    raise ValueError(
                        f"{self.csv_path} {row_number}행 filename이 비어 있습니다."
                    )
                if filename in seen_filenames:
                    raise ValueError(
                        f"{self.csv_path}에 중복 filename이 있습니다: {filename}"
                    )
                seen_filenames.add(filename)

                image_path = self.folder_path / filename
                if not image_path.is_file():
                    missing_files.append(str(image_path))
                    continue

                labels = [
                    _parse_binary_label(
                        row[header.index(class_name)],
                        csv_path=self.csv_path,
                        row_number=row_number,
                        class_name=class_name,
                    )
                    for class_name in self.class_names
                ]
                if not any(labels):
                    all_negative_rows += 1
                # All-negative rows are valid examples. Dropping them hides
                # false positives and teaches the model that a symbol must exist.
                self.samples.append((str(image_path), labels))

        if strict_missing and missing_files:
            examples = "\n".join(missing_files[:10])
            raise FileNotFoundError(
                f"CSV에는 있지만 누락된 이미지가 {len(missing_files)}개 있습니다.\n"
                + examples
            )
        if not self.samples:
            raise ValueError(f"유효한 샘플이 없습니다: {self.folder_path}")

        self.audit = DatasetAudit(
            csv_rows=csv_rows,
            loaded_rows=len(self.samples),
            all_negative_rows=all_negative_rows,
            missing_files=tuple(missing_files),
        )

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        image_path, labels = self.samples[idx]
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
        except OSError as exc:
            raise ValueError(f"이미지를 디코딩할 수 없습니다: {image_path}") from exc
        if self.transform:
            image = self.transform(image)
        return image, torch.tensor(labels, dtype=torch.float32), image_path

    def class_counts(self) -> Counter:
        counts = Counter()
        for _, labels in self.samples:
            for idx, value in enumerate(labels):
                if value == 1.0:
                    counts[idx] += 1
        return counts
