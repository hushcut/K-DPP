"""A labelled product class supplies no composition and hides no percentages."""

import pytest

from apps.text.parse_label import _classify_metadata_line, build_line_infos, parse_label


@pytest.mark.parametrize("caption", [
    "제품구분: 솜털(다운)제품", "제품 구분 : 솜털 ( 다운 ) 제품",
    "제품구분: 솜털제품", "제품구분: 다운제품",
])
@pytest.mark.parametrize("position", ["before", "after"])
def test_complete_product_category_does_not_become_an_unpaired_fiber(caption, position):
    composition = "겉감: 폴리에스터 100%\n안감: 나일론 100%\n충전재: 솜털 80% 깃털 20%"
    text = f"{caption}\n{composition}" if position == "before" else f"{composition}\n{caption}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"polyester": 100}, "lining": {"nylon": 100},
        "filling": {"down": 80, "feather": 20},
    }
    row = next(info for info in build_line_infos(text) if info.raw == caption.lower())
    assert row.is_metadata and not row.materials and not row.numbers
    assert caption in result["raw_ocr_preview"]


@pytest.mark.parametrize("caption", [
    "제품구분: 솜털(다운)제품 100%", "제품구분: 솜털(다운)제품 5",
    "제품구분: 솜털(다운)제품 UNKNOWN", "제품구분: 솜털(다운)제품 NOT",
    "제품구분: 솜털(다운)제품 면 50%", "제품구분: 솜털(다운)제품 / 겉감:면100%",
    "제품구분: 인조 솜털(다운)제품", "제품구분: 솜털(UNKNOWN)제품",
    "제품구분: 솜털(다운제품", "제품구분: 솜털(다운)제품?",
    "제품구분: 솜털(다운)제품 30°C", "제품구분: UNKNOWN",
    "NOT 제품구분: 솜털(다운)제품", "솜털(다운)제품", "솜털 80% 깃털20%",
])
def test_ratios_unknown_words_and_incomplete_captions_are_not_discarded(caption):
    assert _classify_metadata_line(caption, None) == (False, None)


def test_product_category_never_supplies_a_missing_composition():
    assert parse_label("제품구분: 솜털(다운)제품")["status"] == "failed"
    result = parse_label("제품구분: 솜털(다운)제품\n겉감: 면 90%\n안감: 나일론100%")
    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_other_fiber_or_ratio_below_the_caption_remains_evidence():
    text = "제품구분: 솜털(다운)제품\n겉감: 면 100%\nUNKNOWN 5%"
    assert parse_label(text)["status"] == "failed"


def test_empty_product_header_does_not_hide_the_next_row():
    assert _classify_metadata_line("제품구분:", None) == (False, None)
    result = parse_label("제품구분:\nUNKNOWN 100%\n겉감: 면 100%")
    assert "generic" in result["parse_evidence"]["rejected_composition_parts"]
