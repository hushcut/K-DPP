"""Raw numeric precision and the API's exact total agree across boundaries."""

from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from apps.service.response_contract import normalize_label_response
from apps.text.parse_label import normalize_percentages, parse_label
from apps.text.qa_dataset import QaDatasetError, load_qa_answer_key, parse_answer_materials
from apps.text.ratio_contract import has_exact_total


@pytest.mark.parametrize("ratio", ["99.995", "100.000000000000001", "99.999999999999999"])
def test_parser_does_not_round_raw_ratio_into_100(ratio):
    result = parse_label(f"COTTON {ratio}%")
    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_decimal_total_is_not_rounded_by_the_process_context():
    with localcontext() as context:
        context.prec = 5
        assert not has_exact_total([Decimal("100"), Decimal("0.00000000000000000000000001")])
        assert has_exact_total([Decimal("99.99999999999999999999999999"), Decimal("0.00000000000000000000000001")])


def test_exact_ratio_normalization_keeps_decimal_input_precision():
    assert normalize_percentages({"cotton": Decimal("100.000000000000001")}) == {}
    assert normalize_percentages({"cotton": 98.7, "spandex": 1.3}) == {"cotton": 98.7, "spandex": 1.3}


@pytest.mark.parametrize("field", ["materials", "parts"])
def test_response_rejects_near_total(field):
    payload = {"status": "success", "materials": {"cotton": 100}}
    payload[field] = {"cotton": 99.995} if field == "materials" else {"outer": {"cotton": 99.995}}
    with pytest.raises(ValidationError):
        normalize_label_response(payload, api_version="1.0")


@pytest.mark.parametrize("ratio", ["99.995", "100.000000000000001", "99.999999999999999"])
def test_answer_key_rejects_near_total_before_float_conversion(ratio):
    with pytest.raises(QaDatasetError):
        parse_answer_materials({"answer_materials": "cotton", "answer_ratios": ratio}, row_number=2)


def test_loader_validates_original_raw_precision(tmp_path):
    path = tmp_path / "answers.csv"
    path.write_text("file_name,answer_materials,answer_ratios\nlabel.jpg,cotton,100.000000000000001\n", encoding="utf-8")
    with pytest.raises(QaDatasetError):
        load_qa_answer_key(path)


def test_unrepresentable_output_is_rejected_instead_of_rounding_ratios():
    ratios = {"cotton": Decimal("99.999999999999999999"), "spandex": Decimal("0.000000000000000001")}
    assert has_exact_total(ratios.values())
    assert normalize_percentages(ratios) == {}
    result = parse_label("COTTON 99.999999999999999999% SPANDEX 0.000000000000000001%")
    assert result["status"] == "failed"
    assert "generic:ratio_precision_loss" in result["warnings"]


def test_parser_public_response_handles_unrepresentable_three_way_composition():
    result = parse_label(
        "COTTON 33.333333333333333333% "
        "POLYESTER 33.333333333333333333% "
        "SPANDEX 33.333333333333333334%"
    )
    response = normalize_label_response(result, api_version="1.0")
    assert response["status"] == "failed"
    assert response["materials"] == {}
    assert "generic:ratio_precision_loss" in response["warnings"]


def test_answer_key_rejects_unrepresentable_three_way_composition():
    with pytest.raises(QaDatasetError, match="정밀도"):
        parse_answer_materials(
            {
                "answer_materials": "cotton;polyester;spandex",
                "answer_ratios": "33.333333333333333333;33.333333333333333333;33.333333333333333334",
            },
            row_number=2,
        )
