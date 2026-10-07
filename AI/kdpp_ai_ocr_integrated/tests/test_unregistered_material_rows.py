"""미등록 소재의 독립 비율 행을 버리지 않는지 검사한다."""
import pytest
from fastapi.testclient import TestClient

from apps.service.label_analysis import analyze_label_text
from apps.service.main import app
from apps.text.parse_label import parse_label, parse_materials

@pytest.mark.parametrize("unknown_row", [
    "OLEFIN 50%", "POLYPROPYLENE 50%", "올레핀 50%", "아라미드 50%",
    "50% OLEFIN", "OTHER FIBER 50%", "FIBER CONTENT: OLEFIN 50%", "50% 올레핀", "OLEFIN .5%",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_unregistered_fiber_percentage_blocks_same_part(unknown_row, placement):
    text = f"{unknown_row}\nCOTTON 100%" if placement == "before" else f"COTTON 100%\n{unknown_row}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert parse_materials(text) == {}
    assert sorted(result["parse_evidence"]["observed_ratios"]["generic"]) == sorted(
        [100.0, .5 if unknown_row == "OLEFIN .5%" else 50.0]
    )

@pytest.mark.parametrize("unknown_row", [
    "OLEFIN 0%", "OLEFIN -5%", "OLEFIN 101%",
    "OLEFIN 100.000000000000000001%", "OLEFIN 1..5%",
    "0% OLEFIN", "-5% OLEFIN", "101% OLEFIN",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_invalid_unknown_fiber_percentage_cannot_disappear(unknown_row, placement):
    text = f"{unknown_row}\nCOTTON 100%" if placement == "before" else f"COTTON 100%\n{unknown_row}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert parse_materials(text) == {}


@pytest.mark.parametrize("unknown_row", [
    "품번 AB123 OLEFIN 50%", "OLEFIN 50% 품번 AB123",
    "제조국 중국 OLEFIN 50%", "OLEFIN 50% 제조국 중국",
    "제조년월 2024년 OLEFIN 50%", "OLEFIN 50% 제조년월 2024년",
    "製造年月 2024 OLEFIN 50%", "OLEFIN 50% 製造年月 2024",
    "2024 OLEFIN 50%", "OLEFIN 50% 2024",
    "호칭 OLEFIN 0%", "호칭 57% OLEFIN 38%",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_metadata_on_unknown_percentage_row_cannot_hide_composition(unknown_row, placement):
    text = f"{unknown_row}\nCOTTON 100%" if placement == "before" else f"COTTON 100%\n{unknown_row}"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
    assert parse_materials(text) == {}


@pytest.mark.parametrize("unknown_row", [
    "OLEFIN 101%", "OLEFIN 1..5%", "품번 AB123 OLEFIN 50%",
])
def test_invalid_unknown_outer_remains_evidence_when_confirmed_lining_is_selected(unknown_row):
    result = parse_label(f"OUTER {unknown_row}\nLINING COTTON 100%")
    assert result["status"] == "success", result
    assert result["selected_part"] == "lining"
    assert result["materials"] == {"cotton": 100}
    assert "outer" not in result["parts"]
    assert "outer" in result["parse_evidence"]["rejected_composition_parts"]


@pytest.mark.parametrize("unknown_row", [
    "OLEFIN 101%", "OLEFIN 1..5%", "품번 AB123 OLEFIN 50%",
])
def test_invalid_unknown_lining_keeps_confirmed_outer(unknown_row):
    result = parse_label(f"OUTER COTTON 100%\nLINING {unknown_row}")
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 100}
    assert result["parts"] == {"outer": {"cotton": 100}}
    assert any(warning.startswith("lining:") for warning in result["warnings"])


def test_unknown_outer_is_preserved_when_confirmed_lining_is_selected():
    result = parse_label("OUTER OLEFIN 100%\nLINING COTTON 100%")
    assert result["status"] == "success"
    assert result["selected_part"] == "lining"
    assert result["materials"] == {"cotton": 100}
    assert "outer" not in result["parts"]
    assert "outer:unresolved_material_token" in result["warnings"]

def test_unknown_generic_is_preserved_when_confirmed_lining_is_selected():
    result = parse_label("OLEFIN 100%\nLINING COTTON 100%")
    assert result["status"] == "success"
    assert result["selected_part"] == "lining"
    assert result["materials"] == {"cotton": 100}
    assert "generic" not in result["parts"]
    assert "generic:unresolved_material_token" in result["warnings"]

def test_unknown_lining_keeps_confirmed_outer_and_warning():
    result = parse_label("OUTER COTTON 100%\nLINING OLEFIN 100%")
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 100}
    assert "lining" not in result["parts"]
    assert "lining:unresolved_material_token" in result["warnings"]

@pytest.mark.parametrize("metadata", [
    "SIZE 100", "SIZE\n100", "사이즈 100",
    "SHRINKAGE 3%", "SHRINKAGE\n3%", "수축률 3% 이하",
    "WASH AT 30°C", "세탁 온도 30도", "WASH IN 100% COLD WATER",
    "COTTON FEEL 100%", "품번 AB1234", "제조년월 2024년",
    "제조국 중국", "製造年月 2024", "2024", "STYLE AB123 OLEFIN",
    "호칭 57% 38% 5%",
])
def test_explicit_metadata_does_not_block_confirmed_composition(metadata):
    result = parse_label(f"COTTON 100%\n{metadata}")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}

@pytest.mark.parametrize("text, materials", [
    ("COTTON 80% POLYESTER 20%", {"cotton": 80, "polyester": 20}),
    ("COTTON 80%\nPOLYESTER 20%", {"cotton": 80, "polyester": 20}),
    ("COTTON\nPOLYESTER\n80%\n20%", {"cotton": 80, "polyester": 20}),
    ("COTTON 100%\n면 100%", {"cotton": 100}),
    ("COTTON 98.7% SPANDEX 1.3%", {"cotton": 98.7, "spandex": 1.3}),
    ("품번 AB123 COTTON 100%", {"cotton": 100}),
    ("COTTON 100% 품번 AB123", {"cotton": 100}),
    ("제조년월 2024년 COTTON 100%", {"cotton": 100}),
    ("COTTON 100% 제조년월 2024년", {"cotton": 100}),
])
def test_supported_compositions_are_preserved(text, materials):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == materials


@pytest.mark.parametrize("text", [
    "COTTON 100%\nOLEFIN 50%",
    "OUTER OLEFIN 100%\nLINING COTTON 100%",
    "COTTON 100%\nOLEFIN 0%",
    "COTTON 100%\nOLEFIN -5%",
    "COTTON 100%\nOLEFIN 101%",
    "COTTON 100%\nOLEFIN 100.000000000000000001%",
    "COTTON 100%\nOLEFIN 1..5%",
    "COTTON 100%\n품번 AB123 OLEFIN 50%",
    "COTTON 100%\nOLEFIN 50% 2024",
])
def test_unregistered_fiber_preserves_selected_part_and_service_response_contract(text):
    response = analyze_label_text(text)
    fallback = text.startswith("OUTER")
    expected_status = "success" if fallback else "failed"
    assert response["status"] == expected_status
    assert response["materials"] == ({"cotton": 100} if fallback else {})
    assert response["selected_part"] == ("lining" if fallback else "")
    assert response["parts"] == ({"lining": {"cotton": 100}} if fallback else {})
    with TestClient(app, raise_server_exceptions=False) as client:
        result = client.post("/v1/parse-text", json={"text": text})
    assert result.status_code == (200 if fallback else 422)
    body = result.json()
    assert body["status"] == expected_status
    assert body["materials"] == response["materials"]
    assert body["parts"] == response["parts"]
    assert body["selected_part"] == response["selected_part"]
    if fallback:
        assert "outer:unresolved_material_token" in body["warnings"]


@pytest.mark.parametrize("text", [
    "COTTON 100%\nOLEFIN",
    "COTTON 100%\nCOMPOSITION",
])
def test_unquantified_text_is_not_treated_as_an_unknown_percentage(text):
    result = parse_label(text)
    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
