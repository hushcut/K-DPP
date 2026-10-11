"""숫자 검증 실패를 QA 성공으로 처리하지 않는 회귀 검사."""

import pytest

from apps.text.qa_comparison import (
    QaComparisonError,
    compare_material_compositions,
    normalize_material_mapping,
)


@pytest.mark.parametrize("tolerance", [float("nan"), float("inf"), -float("inf"), -1, True, "3"])
def test_invalid_tolerance_cannot_make_a_wrong_composition_succeed(tolerance) -> None:
    with pytest.raises(QaComparisonError, match="허용 오차"):
        compare_material_compositions({"cotton": 100}, {"cotton": 1}, tolerance=tolerance)


@pytest.mark.parametrize("ratio", ["100", True, False, float("nan"), float("inf"), -1, 0, 101])
def test_invalid_material_ratios_cannot_be_normalized(ratio) -> None:
    with pytest.raises(QaComparisonError):
        normalize_material_mapping({"cotton": ratio})


def test_alias_aggregation_cannot_exceed_100_percent() -> None:
    with pytest.raises(QaComparisonError):
        normalize_material_mapping({"cotton": 80, "면": 30})


def test_normal_aliases_and_decimal_tolerance_remain_supported() -> None:
    comparison = compare_material_compositions(
        {"cotton": 99.5, "spandex": 0.5},
        {"면": 99.25, "elastane": 0.75},
        tolerance=0.25,
    )
    assert comparison.judgment == "success"
    assert normalize_material_mapping({"cotton": 50, "면": 50}) == {"cotton": 100.0}
    assert compare_material_compositions(
        {"cotton": 100}, {"cotton": 99}, tolerance=0,
    ).judgment == "failed"


def test_small_positive_ratios_and_differences_keep_their_precision() -> None:
    expected = {"cotton": 99.99999, "spandex": 0.00001}
    actual = {"cotton": 99.99998, "spandex": 0.00002}
    assert normalize_material_mapping(expected) == expected
    comparison = compare_material_compositions(expected, actual, tolerance=0)
    assert comparison.judgment == "failed"
    assert comparison.ratio_differences["spandex"] == 0.00001
    assert "spandex:+1e-05" in comparison.failure_reason
