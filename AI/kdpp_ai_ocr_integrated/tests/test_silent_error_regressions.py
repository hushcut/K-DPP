import json
from pathlib import Path

from apps.text import ocr_text
from apps.text.parse_label import build_line_infos, parse_label


def test_cached_silent_error_cases_fail_safely() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "cached_ocr_silent_error_cases.json"
    )
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    for case in cases:
        assert parse_label(case["text"])["status"] == "failed", case["id"]


def test_does_not_reuse_one_explicit_ratio_for_multiple_materials() -> None:
    text = """품질표시
폴리우레탄
폴리에스터
나일론
68%
17
15"""

    assert parse_label(text)["status"] == "failed"


def test_does_not_promote_partial_single_material_to_100_percent() -> None:
    result = parse_label("섬유의 조성 및 혼용률\n소재: 면 80%")

    assert result["status"] == "failed"


def test_does_not_promote_single_material_95_percent_to_100_percent() -> None:
    result = parse_label("섬유의 조성 및 혼용률\n소재: 면 95%")

    assert result["status"] == "failed"


def test_does_not_normalize_excessive_total() -> None:
    result = parse_label("면 80% 폴리에스터 50%")

    assert result["status"] == "failed"


def test_rejects_mismatched_material_and_ratio_counts() -> None:
    result = parse_label("면\n폴리에스터\n나일론\n50%\n50%")

    assert result["status"] == "failed"


def test_preserves_separate_parts_when_both_are_valid() -> None:
    result = parse_label("겉감: 면 100%\n배색: 면 95%, 폴리우레탄 5%")

    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"cotton": 100},
        "color_block": {"cotton": 95, "polyurethane": 5},
    }


def test_splits_compound_part_and_material_token() -> None:
    result = parse_label("배색면\n95%\n폴리우레탄 5%")

    assert result["status"] == "success"
    assert result["selected_part"] == "color_block"
    assert result["materials"] == {"cotton": 95, "polyurethane": 5}


def test_ignores_bare_care_numbers_after_a_part_marker() -> None:
    infos = build_line_infos("배색면\n95%\n폴리우레탄 5%\n80-12 ℃")

    care_line = next(
        info for info in infos if info.normalized.startswith("80-12")
    )
    assert care_line.numbers == ()


def test_recognizes_unambiguous_truncated_polyester_alias() -> None:
    result = parse_label("면 80%, 폴리에스 20%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 80, "polyester": 20}


def test_keeps_valid_column_layout_composition() -> None:
    result = parse_label("폴리에스터\n폴리우레탄\n94%\n6%")

    assert result["status"] == "success"
    assert result["materials"] == {"polyester": 94, "polyurethane": 6}
    assert result["parse_evidence"]["source"] == "stacked_columns"


def test_ocr_candidate_prefers_complete_explicit_evidence() -> None:
    partial_original = ocr_text._build_candidate("original", "COTTON 80%")
    complete_preprocessed = ocr_text._build_candidate(
        "preprocessed",
        "COTTON 80% POLYESTER 20%",
    )

    best = max(
        [partial_original, complete_preprocessed],
        key=lambda candidate: candidate.score,
    )

    assert best.source == "preprocessed"


def test_ocr_candidate_does_not_treat_mismatched_counts_as_complete() -> None:
    candidate = ocr_text._build_candidate(
        "original",
        "COTTON POLYESTER NYLON 50% 50%",
    )

    assert candidate.parser_status == "failed"
    assert candidate.score[0] == 0
    assert candidate.score[1] == 0


def test_composition_on_heading_line_beats_later_unlabeled_candidate() -> None:
    result = parse_label("MATERIAL: COTTON 100%\nPOLYESTER 100%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}


def test_material_touch_marketing_phrase_is_not_composition() -> None:
    result = parse_label("SILK TOUCH 100%")

    assert result["status"] == "failed"
    assert result["materials"] == {}
