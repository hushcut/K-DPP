"""중국어 소재명의 OCR 공백·줄 분할 복원과 경계 보존 검사."""

import pytest

from apps.text.material_extraction import normalize_text
from apps.text.ocr_candidates import build_candidate, find_rejected_composition_parts
from apps.text.parse_label import parse_label


@pytest.mark.parametrize("text, expected", [
    ("聚酯 纤维 100 %", {"polyester": 100}),
    (
        "人造 丝 45 %\n锦纶 28 %\n聚酯 纤维 22 %\n聚氨酯 5 %",
        {"rayon": 45, "nylon": 28, "polyester": 22, "polyurethane": 5},
    ),
    (
        "聚酯 纤维\n75 %\n人造 丝\n21 %\n氨纶 4 %",
        {"polyester": 75, "rayon": 21, "spandex": 4},
    ),
    (
        "面料\n棉 51 %\n聚酯 纤维 46 %\n聚氨酯 3 %",
        {"cotton": 51, "polyester": 46, "polyurethane": 3},
    ),
    ("100% 聚酯\n纤维", {"polyester": 100}),
    ("聚\n酯\n纤\n维 100%", {"polyester": 100}),
    ("人造\n丝 100%", {"rayon": 100}),
    ("聚酯\n纖維 100%", {"polyester": 100}),
    ("人造\n絲 100%", {"rayon": 100}),
    ("粘 胶 纤 维 100%", {"viscose": 100}),
    ("聚酰胺\n纤维 100%", {"nylon": 100}),
    ("聚氨酯弹性\n纤维 100%", {"spandex": 100}),
    ("聚氨酯 弹性纤维 100%", {"spandex": 100}),
    ("面料聚酯 纤维100%", {"polyester": 100}),
    ("聚酯\t纤维１００％", {"polyester": 100}),
])
def test_split_registered_chinese_fiber_and_ratio_are_restored(text, expected):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == expected


@pytest.mark.parametrize("text", [
    "聚氨酯\n弹性纤维 100%",
    "聚\n氨酯\n弹性纤维 100%",
    "聚氨酯\n彈性纖維 100%",
    "聚酯\n里料\n纤维 100%",
    "聚酯\n尺码\n纤维 100%",
    "聚酯 50%\n纤维 50%",
    "聚酯 / 纤维 100%",
    "聚酯 纤维X 100%",
    "未知聚酯 纤维 100%",
    "聚酯 纤维 100%\n未知纤维 10%",
    "聚酯 纤维 100%\n10%",
    "聚酯 纤维 130%",
    "聚酯 纤维 95%\n氨纶 -5%",
    "聚酯 纤维 99%",
    "人造\n皮革 100%",
])
def test_chinese_restoration_preserves_other_fibers_and_invalid_evidence(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_chinese_restoration_keeps_outer_and_lining_separate():
    result = parse_label("面料 聚酯 纤维 100%\n里料 人造 丝 100%")
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 100}
    assert result["selected_part"] == "outer"


def test_chinese_restoration_keeps_polyurethane_distinct_from_spandex():
    result = parse_label("聚酯 纤维 90%\n聚氨酯 5%\n氨纶 5%")
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 90, "polyurethane": 5, "spandex": 5}


def test_equivalent_spaced_chinese_candidate_is_no_longer_rejected():
    candidates = [
        build_candidate("original", "聚酯纤维 100%", parse_candidate=parse_label),
        build_candidate("preprocessed", "聚酯 纤维 100%", parse_candidate=parse_label),
    ]
    assert all(candidate.parser_status == "success" for candidate in candidates)
    assert not find_rejected_composition_parts(candidates, selected_part="generic")


def test_same_line_normalization_does_not_remove_other_row_boundaries():
    assert normalize_text("面料 聚酯 纤维 100%\n里料 人造 丝 100%") == (
        "面料 聚酯纤维 100%\n里料 人造丝 100%"
    )
    assert normalize_text("聚酯\n纤维 100%") == "聚酯\n纤维 100%"
