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

def test_unknown_outer_does_not_fall_back_to_confirmed_lining():
    result = parse_label("OUTER OLEFIN 100%\nLINING COTTON 100%")
    assert result["status"] == "failed"
    assert result["materials"] == {}

def test_unknown_generic_does_not_fall_back_to_confirmed_lining():
    result = parse_label("OLEFIN 100%\nLINING COTTON 100%")
    assert result["status"] == "failed"
    assert result["materials"] == {}

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
])
def test_supported_compositions_are_preserved(text, materials):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == materials


@pytest.mark.parametrize("text", [
    "COTTON 100%\nOLEFIN 50%",
    "OUTER OLEFIN 100%\nLINING COTTON 100%",
])
def test_unregistered_fiber_failure_preserves_service_response_contract(text):
    response = analyze_label_text(text)
    assert response["status"] == "failed"
    assert response["materials"] == {}
    assert response["parts"] == {}
    assert response["selected_part"] == ""
    with TestClient(app, raise_server_exceptions=False) as client:
        result = client.post("/v1/parse-text", json={"text": text})
    assert result.status_code == 422
    assert result.json()["materials"] == {}


@pytest.mark.parametrize("text", [
    "COTTON 100%\nOLEFIN",
    "COTTON 100%\nCOMPOSITION",
])
def test_unquantified_text_is_not_treated_as_an_unknown_percentage(text):
    result = parse_label(text)
    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
