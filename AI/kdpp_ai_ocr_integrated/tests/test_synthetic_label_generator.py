import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.synthetic.label_generator import generate_dataset


def test_config(output_dir: Path) -> dict:
    return {
        "dataset_name": "unit_test",
        "generator_version": "test",
        "seed": 1234,
        "base_label_count": 3,
        "variants_per_label": 2,
        "image_width": 640,
        "image_height": 480,
        "languages": ["en"],
        "layouts": ["material_first", "ratio_first", "stacked_columns"],
        "conditions": ["clean", "rotated", "blur"],
        "themes": ["white", "black"],
        "part_label_probability": 0.5,
        "materials": ["cotton", "polyester", "nylon", "spandex", "wool"],
        "jpeg_quality_min": 85,
        "jpeg_quality_max": 90,
        "contact_sheet_limit": 6,
        "output_dir": str(output_dir),
    }


class SyntheticLabelGeneratorTests(unittest.TestCase):
    def test_generates_expected_files_and_valid_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "dataset"
            summary = generate_dataset(test_config(output))

            self.assertEqual(summary["images"], 6)
            self.assertEqual(summary["unique_source_groups"], 3)
            self.assertEqual(summary["unique_image_hashes"], 6)
            self.assertTrue((output / "manifest.csv").is_file())
            self.assertTrue((output / "summary.json").is_file())
            self.assertTrue((output / "contact_sheet.jpg").is_file())

            with (output / "manifest.csv").open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))

            self.assertEqual(len(rows), 6)
            for row in rows:
                ratios = [int(value) for value in row["answer_ratios"].split(";")]
                self.assertEqual(sum(ratios), 100)
                self.assertTrue((output / "images" / row["file_name"]).is_file())
                self.assertEqual(row["split"], "unassigned")
                self.assertEqual(len(row["image_sha256"]), 64)
                self.assertIn(row["selected_part"], {"generic", "outer"})
                self.assertIsInstance(json.loads(row["parts_json"]), dict)

    def test_same_seed_produces_same_image_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first"
            second = root / "second"
            generate_dataset(test_config(first))
            generate_dataset(test_config(second))

            def hashes(path: Path) -> list[str]:
                with (path / "manifest.csv").open("r", encoding="utf-8-sig", newline="") as stream:
                    return [row["image_sha256"] for row in csv.DictReader(stream)]

            self.assertEqual(hashes(first), hashes(second))

    def test_refuses_to_write_into_non_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "dataset"
            output.mkdir()
            (output / "keep.txt").write_text("do not overwrite", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                generate_dataset(test_config(output))


if __name__ == "__main__":
    unittest.main()
