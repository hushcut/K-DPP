"""Joined literal translations must agree and account for every character."""

import pytest

from apps.text.material_extraction import extract_materials, find_material_key
from apps.text.parse_label import parse_label


@pytest.mark.parametrize("alias,material", [
    ("綿コットン", "cotton"), ("コットン綿", "cotton"),
    ("羊毛ウール", "wool"), ("ウール羊毛", "wool"),
    ("絹シルク", "silk"), ("シルク絹", "silk"),
])
@pytest.mark.parametrize("order", ["ratio_first", "ratio_last"])
def test_two_complete_translations_are_one_fiber(alias, material, order):
    text = f"100% {alias}" if order == "ratio_first" else f"{alias} 100%"
    result = parse_label(text)
    assert find_material_key(alias) == material
    assert extract_materials(text) == [material]
    assert result["status"] == "success", result
    assert result["materials"] == {material: 100}
    assert alias in result["raw_ocr_preview"]


@pytest.mark.parametrize("alias", [
    "綿ウール", "羊毛コットン", "絹コットン", "綿コットン混", "未知コットン",
    "非綿コットン", "人造綿コットン", "コットン未知", "綿コットンUNKNOWN",
    "NOT綿コットン", "綿コットン綿", "綿コットンウール",
])
def test_different_fibers_and_unknown_characters_are_never_discarded(alias):
    assert find_material_key(alias) is None
    result = parse_label(f"{alias}100%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_a_translation_does_not_supply_a_ratio_or_hide_other_fibers():
    assert parse_label("綿コットン")["status"] == "failed"
    result = parse_label("綿コットン95% ポリウレタン5%")
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 95, "polyurethane": 5}
    assert parse_label("綿コットン100%\n未知繊維5%")["status"] == "failed"


def test_an_unknown_outer_cannot_borrow_a_valid_lining():
    result = parse_label("表地:綿ウール100%\n裏地:コットン綿100%")
    assert result["status"] == "failed" and result["materials"] == {}


def test_joined_translation_and_original_text_keep_the_declared_outer():
    text = "シェル:100%綿コットン/装飾部分を除く\n裏地:ポリエステル100%"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["parts"] == {"outer": {"cotton": 100}, "lining": {"polyester": 100}}
    assert "綿コットン" in result["raw_ocr_preview"]
