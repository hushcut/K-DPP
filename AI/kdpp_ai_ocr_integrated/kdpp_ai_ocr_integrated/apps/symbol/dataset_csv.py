import os
from collections import Counter

import pandas as pd
from PIL import Image
import torch
from torch.utils.data import Dataset


class SymbolCsvDataset(Dataset):
    def __init__(self, folder_path: str, transform=None):
        self.folder_path = folder_path
        self.csv_path = os.path.join(folder_path, "_classes.csv")
        self.transform = transform

        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"_classes.csv 파일이 없습니다: {self.csv_path}")

        self.df = pd.read_csv(self.csv_path)
        self.df.columns = [col.strip() for col in self.df.columns]
        if "filename" not in self.df.columns:
            raise ValueError("CSV에 'filename' 컬럼이 없습니다.")

        self.class_names = [col for col in self.df.columns if col != "filename"]
        self.samples = []

        for _, row in self.df.iterrows():
            image_path = os.path.join(folder_path, str(row["filename"]))
            if not os.path.exists(image_path):
                continue

            label_values = []
            for index, class_name in enumerate(self.class_names):
                try:
                    value = int(row[class_name])
                except Exception:
                    value = 0
                if value == 1:
                    label_values.append(1.0)
                else:
                    label_values.append(0.0)

            if any(label_values):
                self.samples.append((image_path, label_values))

        if not self.samples:
            raise ValueError(f"유효한 샘플이 없습니다: {folder_path}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        image_path, label_idx = self.samples[idx]
        image = Image.open(image_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, torch.tensor(label_idx, dtype=torch.float32), image_path

    def class_counts(self) -> Counter:
        counts = Counter()
        for _, labels in self.samples:
            for idx, value in enumerate(labels):
                if value == 1.0:
                    counts[idx] += 1
        return counts
