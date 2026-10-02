import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import ImageDraw

from apps.synthetic.label_generator import (
    LabelSpec,
    _draw_label,
    build_specs,
    generate_dataset,
    label_text,
    load_config,
)
from apps.text.parse_label import parse_label


def generator_config() -> dict:
    return {
        "version": "test-v1",
        "seed": 7,
        "base_label_count": 2,
        "variants_per_label": 2,
        "languages": ["en"],
        "conditions": ["clean", "blur"],
        "layouts": ["material_first"],
        "themes": ["white"],
        "materials": ["cotton", "polyester", "rayon"],
        "lining_probability": 0.0,
        "image_width": 400,
        "image_height": 240,
        "font_size": 20,
        "jpeg_quality_min": 90,
        "jpeg_quality_max": 90,
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


def controlled_generator_config() -> dict:
    config = generator_config()
    config.update(
        {
            "variants_per_label": 5,
            "conditions": ["clean"],
            "layouts": ["material_first", "ratio_first", "stacked_columns"],
            "themes": ["white", "ivory", "black"],
            "variant_plan": [
                {
                    "role": "baseline",
                    "condition": "clean",
                    "layout": "material_first",
                    "theme": "white",
                },
                {
                    "role": "layout_ratio_first",
                    "condition": "clean",
                    "layout": "ratio_first",
                    "theme": "white",
                    "comparison_axis": "layout",
                    "comparison_value": "ratio_first",
                },
                {
                    "role": "layout_stacked_columns",
                    "condition": "clean",
                    "layout": "stacked_columns",
                    "theme": "white",
                    "comparison_axis": "layout",
                    "comparison_value": "stacked_columns",
                },
                {
                    "role": "theme_ivory",
                    "condition": "clean",
                    "layout": "material_first",
                    "theme": "ivory",
                    "comparison_axis": "theme",
                    "comparison_value": "ivory",
                },
                {
                    "role": "theme_black",
                    "condition": "clean",
                    "layout": "material_first",
                    "theme": "black",
                    "comparison_axis": "theme",
                    "comparison_value": "black",
                },
            ],
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
    assert {row["layout"] for row in rows} == {"material_first"}
    assert {row["theme"] for row in rows} == {"white"}
    assert {row["jpeg_quality"] for row in rows} == {"90"}
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


def test_generator_covers_layout_theme_and_mixed_condition_metadata(tmp_path) -> None:
    config = generator_config()
    config.update(
        {
            "base_label_count": 3,
            "variants_per_label": 1,
            "conditions": ["mixed"],
            "layouts": ["material_first", "ratio_first", "stacked_columns"],
            "themes": ["white", "ivory", "black"],
            "jpeg_quality_min": 72,
            "jpeg_quality_max": 96,
        }
    )

    output_dir = tmp_path / "diverse"
    generate_dataset(config, output_dir)

    with (output_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    assert {row["layout"] for row in rows} == {
        "material_first",
        "ratio_first",
        "stacked_columns",
    }
    assert {row["theme"] for row in rows} == {"white", "ivory", "black"}
    assert all(72 <= int(row["jpeg_quality"]) <= 96 for row in rows)
    assert all(json.loads(row["transforms_json"])["blur_radius"] == 1.8 for row in rows)
    assert all(parse_label(row["original_text"])["status"] == "success" for row in rows)


def test_generator_creates_paired_control_variants_per_source_group(tmp_path) -> None:
    output_dir = tmp_path / "controls"

    summary = generate_dataset(controlled_generator_config(), output_dir)

    with (output_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    grouped = {
        source_group: [row for row in rows if row["source_group"] == source_group]
        for source_group in {row["source_group"] for row in rows}
    }

    assert summary["variant_role_counts"] == {
        "baseline": 2,
        "layout_ratio_first": 2,
        "layout_stacked_columns": 2,
        "theme_black": 2,
        "theme_ivory": 2,
    }
    for variants in grouped.values():
        by_role = {row["variant_role"]: row for row in variants}
        assert len(by_role) == 5
        assert len({row["parts_json"] for row in variants}) == 1
        assert {row["condition"] for row in variants} == {"clean"}
        assert by_role["baseline"]["layout"] == "material_first"
        assert by_role["baseline"]["theme"] == "white"
        assert by_role["layout_ratio_first"]["comparison_axis"] == "layout"
        assert by_role["layout_stacked_columns"]["comparison_value"] == "stacked_columns"
        assert by_role["theme_ivory"]["comparison_axis"] == "theme"
        assert by_role["theme_black"]["comparison_value"] == "black"


def test_stacked_compositions_are_fully_drawn_inside_the_image(monkeypatch) -> None:
    drawn_boxes = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(draw, position, text, *args, **kwargs):
        drawn_boxes.append(draw.textbbox(position, text, font=kwargs["font"]))
        return original_text(draw, position, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    config_dir = Path(__file__).resolve().parents[1] / "configs"
    for config_name in ("synthetic_labels_v1.json", "synthetic_label_controls_v1.json"):
        config = load_config(config_dir / config_name)
        specs = [replace(spec, layout="stacked_columns") for spec in build_specs(config)]
        specs.append(
            LabelSpec(
                source_group="LONG",
                language="en",
                parts={
                    "outer": {"cotton": 50, "polyester": 30, "nylon": 20},
                    "lining": {"rayon": 40, "wool": 30, "acrylic": 30},
                },
                layout="stacked_columns",
                theme="white",
            )
        )
        margin = max(40, int(min(config["image_width"], config["image_height"]) * 0.125))
        for spec in specs:
            drawn_boxes.clear()
            _draw_label(spec, config)
            assert len(drawn_boxes) == len(label_text(spec).splitlines())
            assert all(
                margin <= box[1] and box[3] <= config["image_height"] - margin
                for box in drawn_boxes
            ), spec.source_group


def test_generator_rejects_unknown_layout(tmp_path) -> None:
    config = generator_config()
    config["layouts"] = ["unsupported"]

    with pytest.raises(ValueError, match="layouts"):
        generate_dataset(config, tmp_path / "invalid")


def test_generator_rejects_control_variant_with_another_changed_axis(tmp_path) -> None:
    config = controlled_generator_config()
    config["variant_plan"][1]["theme"] = "ivory"

    with pytest.raises(ValueError, match="change only"):
        generate_dataset(config, tmp_path / "invalid-controls")


def test_generator_refuses_to_overwrite_nonempty_directory(tmp_path) -> None:
    output_dir = tmp_path / "synthetic"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        generate_dataset(generator_config(), output_dir)
