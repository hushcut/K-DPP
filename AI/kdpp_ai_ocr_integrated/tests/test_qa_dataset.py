import csv

import pytest

from apps.text.qa_dataset import (
    QaDatasetError,
    answer_key_columns,
    audit_qa_answer_key,
    load_qa_answer_key,
    parse_answer_materials,
)


def write_answer_key(tmp_path, rows, fieldnames):
    path = tmp_path / "answer_key.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_answer_key_requires_canonical_material_keys() -> None:
    with pytest.raises(QaDatasetError, match="표준 키"):
        parse_answer_materials(
            {"answer_materials": "polyester;cottonn", "answer_ratios": "80;20"},
            row_number=2,
        )


def test_answer_key_accepts_parser_aliases_but_returns_canonical_keys() -> None:
    assert parse_answer_materials(
        {"answer_materials": "면;elastane", "answer_ratios": "95;5"},
        row_number=2,
    ) == {"cotton": 95.0, "spandex": 5.0}


def test_answer_key_rejects_non_exact_composition() -> None:
    with pytest.raises(QaDatasetError, match="정확히 100"):
        parse_answer_materials(
            {"answer_materials": "cotton;spandex", "answer_ratios": "96;5"},
            row_number=2,
        )


def test_loader_uses_normalized_composition_for_an_included_complex_label(tmp_path) -> None:
    path = write_answer_key(
        tmp_path,
        [
            {
                "file_name": "QA001.jpg",
                "answer_materials": "polyester;acrylic",
                "answer_ratios": "100;60",
                "include_in_accuracy": "TRUE",
                "normalized_materials": "polyester",
                "normalized_ratios": "100",
            },
            {
                "file_name": "QA002.jpg",
                "answer_materials": "nylon;polyester;down;feather",
                "answer_ratios": "100;100;90;10",
                "include_in_accuracy": "FALSE",
            },
        ],
        [
            "file_name",
            "answer_materials",
            "answer_ratios",
            "include_in_accuracy",
            "normalized_materials",
            "normalized_ratios",
        ],
    )

    answers = load_qa_answer_key(path)

    assert answers["QA001.jpg"].materials == {"polyester": 100.0}
    assert answers["QA001.jpg"].original_materials == {
        "polyester": 100.0,
        "acrylic": 60.0,
    }
    assert answers["QA002.jpg"].include_in_accuracy is False


def test_audit_reports_condition_coverage_and_source_group_leakage(tmp_path) -> None:
    path = write_answer_key(
        tmp_path,
        [
            {
                "file_name": "QA001.jpg",
                "answer_materials": "cotton;polyester",
                "answer_ratios": "80;20",
                "split": "train",
                "source_group": "shirt_front",
                "capture_condition": "indoor",
                "label_layout": "same_line",
            },
            {
                "file_name": "QA002.jpg",
                "answer_materials": "cotton",
                "answer_ratios": "100",
                "split": "valid",
                "source_group": "shirt_front",
                "capture_condition": "reflection",
                "label_layout": "stacked",
            },
        ],
        [
            "file_name",
            "answer_materials",
            "answer_ratios",
            "split",
            "source_group",
            "capture_condition",
            "label_layout",
        ],
    )

    answers = load_qa_answer_key(path)
    audit = audit_qa_answer_key(answers, columns=answer_key_columns(path))

    assert audit.answer_count == 2
    assert audit.material_sample_counts == {"cotton": 2, "polyester": 1}
    assert audit.condition_counts == {"indoor": 1, "reflection": 1}
    assert audit.source_group_split_leaks == {"shirt_front": ("train", "valid")}
    assert audit.missing_optional_columns == ()


def test_split_column_requires_an_allowed_value(tmp_path) -> None:
    path = write_answer_key(
        tmp_path,
        [
            {
                "file_name": "QA001.jpg",
                "answer_materials": "cotton",
                "answer_ratios": "100",
                "split": "development",
            }
        ],
        ["file_name", "answer_materials", "answer_ratios", "split"],
    )

    with pytest.raises(QaDatasetError, match="train, valid, test"):
        load_qa_answer_key(path)
