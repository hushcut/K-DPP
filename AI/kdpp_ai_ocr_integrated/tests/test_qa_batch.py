import pytest

from scripts.run_qa_batch import (
    AnswerKeyError,
    compare_materials,
    parse_answer_materials,
)


def test_answer_key_materials_and_ratios_must_align() -> None:
    with pytest.raises(AnswerKeyError):
        parse_answer_materials(
            {
                "answer_materials": "cotton;polyester",
                "answer_ratios": "100",
            },
            row_number=2,
        )


def test_answer_key_ratio_total_must_be_100() -> None:
    with pytest.raises(AnswerKeyError):
        parse_answer_materials(
            {
                "answer_materials": "cotton;polyester",
                "answer_ratios": "80;10",
            },
            row_number=2,
        )


def test_compare_materials_reports_missing_extra_and_ratio_errors() -> None:
    judgment, reason = compare_materials(
        {"cotton": 80, "polyester": 20},
        {"cotton": 70, "acrylic": 30},
        tolerance=2.0,
    )

    assert judgment == "failed"
    assert "missing=polyester" in reason
    assert "extra=acrylic" in reason
    assert "ratio_diff=cotton:-10.0" in reason

