import csv
from pathlib import Path

import pytest

from apps.synthetic.label_generator import generate_dataset


def generator_config() -> dict:
    return {
        "version": "test-v1",
        "seed": 7,
        "base_label_count": 2,
        "variants_per_label": 2,
        "languages": ["en"],
        "conditions": ["clean", "blur"],
        "materials": ["cotton", "polyester", "rayon"],
        "lining_probability": 0.0,
        "image_width": 400,
        "image_height": 240,
        "font_size": 20,
    }


def multilingual_generator_config() -> dict:
    config = generator_config()
    config.update(
        {
            "base_label_count": 4,
            "variants_per_label": 1,
            "languages": ["ko", "en", "ja", "zh"],
            "conditions": ["clean"],
        }
    )
    return config


def test_generator_writes_manifest_images_and_group_metadata(tmp_path) -> None:
    output_dir = tmp_path / "synthetic"

    summary = generate_dataset(generator_config(), output_dir)

    with (output_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert summary["image_count"] == 4
    assert len(rows) == 4
    assert {row["source_group"] for row in rows} == {"SYN0001", "SYN0002"}
    assert {row["include_in_accuracy"] for row in rows} == {"false"}
    assert {row["split"] for row in rows} == {"unassigned"}
    assert all((output_dir / "images" / row["file_name"]).is_file() for row in rows)
    assert (output_dir / "contact_sheet.jpg").is_file()


def test_generator_supports_all_default_languages(tmp_path) -> None:
    output_dir = tmp_path / "multilingual"

    generate_dataset(multilingual_generator_config(), output_dir)

    with (output_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert {row["language"] for row in rows} == {"ko", "en", "ja", "zh"}
    assert all(row["font"] != "Pillow-default" for row in rows)


def test_same_seed_generates_identical_image_hashes(tmp_path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    generate_dataset(generator_config(), first_dir)
    generate_dataset(generator_config(), second_dir)

    def hashes(directory: Path) -> list[str]:
        with (directory / "manifest.csv").open(encoding="utf-8-sig", newline="") as file:
            return [row["image_sha256"] for row in csv.DictReader(file)]

    assert hashes(first_dir) == hashes(second_dir)


def test_generator_refuses_to_overwrite_nonempty_directory(tmp_path) -> None:
    output_dir = tmp_path / "synthetic"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        generate_dataset(generator_config(), output_dir)
