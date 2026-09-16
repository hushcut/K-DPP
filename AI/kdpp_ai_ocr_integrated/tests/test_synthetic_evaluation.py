import csv

from apps.synthetic.evaluation import evaluate_manifest, write_evaluation
from apps.synthetic.label_generator import generate_dataset


def evaluation_config() -> dict:
    return {
        "version": "evaluation-test-v1",
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


def controlled_evaluation_config() -> dict:
    config = evaluation_config()
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


def test_synthetic_evaluation_writes_image_and_source_group_scores(tmp_path) -> None:
    dataset_dir = tmp_path / "dataset"
    generate_dataset(evaluation_config(), dataset_dir)

    results, group_results, summary = evaluate_manifest(dataset_dir / "manifest.csv")
    output_dir = write_evaluation(tmp_path / "evaluation", results, group_results, summary)

    assert summary["evaluation_type"] == "synthetic_parser_only"
    assert summary["ocr_called"] is False
    assert summary["image_count"] == 4
    assert summary["image_exact_composition_accuracy"] == 1.0
    assert summary["source_group_count"] == 2
    assert summary["source_group_all_variants_accuracy"] == 1.0
    assert "by_layout" not in summary
    assert "by_theme" not in summary
    assert (output_dir / "image_results.csv").is_file()
    assert (output_dir / "source_group_results.csv").is_file()


def test_synthetic_evaluation_compares_only_paired_control_variants(tmp_path) -> None:
    dataset_dir = tmp_path / "dataset"
    generate_dataset(controlled_evaluation_config(), dataset_dir)

    _, _, summary = evaluate_manifest(dataset_dir / "manifest.csv")

    comparisons = summary["controlled_comparisons"]
    assert comparisons["layout"]["ratio_first"]["pair_count"] == 2
    assert comparisons["layout"]["stacked_columns"][
        "comparison_exact_composition_accuracy"
    ] == 1.0
    assert comparisons["theme"]["ivory"]["baseline_exact_composition_accuracy"] == 1.0
    assert comparisons["theme"]["black"]["both_exact_composition_count"] == 2


def test_source_group_score_fails_when_one_variant_parser_fails(tmp_path) -> None:
    dataset_dir = tmp_path / "dataset"
    generate_dataset(evaluation_config(), dataset_dir)
    manifest_path = dataset_dir / "manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    rows[0]["original_text"] = "not a composition"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    _, group_results, summary = evaluate_manifest(manifest_path)

    assert summary["image_exact_composition_accuracy"] == 0.75
    assert summary["source_group_all_variants_accuracy"] == 0.5
    assert [row["group_judgment"] for row in group_results].count("failed") == 1
