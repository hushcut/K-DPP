"""Printed outer-fabric indices must not become ratios or merge fabrics."""

import pytest

from apps.text.material_extraction import declared_part
from apps.text.parse_label import build_line_infos, parse_label


@pytest.mark.parametrize("heading", ["面料", "表地"])
@pytest.mark.parametrize("separator", ["", " ", "\t"])
@pytest.mark.parametrize("index,part", [("1", "outer"), ("2", "outer_2")])
def test_literal_cjk_fabric_index_names_its_own_part(heading, separator, index, part):
    marker = f"{heading}{separator}{index}"
    result = parse_label(f"{marker}: 100%\nNYLON")
    assert declared_part(marker) == part
    assert result["status"] == "success", result
    assert result["parts"] == {part: {"nylon": 100}}


@pytest.mark.parametrize("heading", ["面料", "表地"])
def test_numbered_cjk_fabrics_keep_distinct_compositions(heading):
    result = parse_label(
        f"{heading} 1\nCOTTON 50% POLYESTER 50%\n"
        f"{heading} 2\nNYLON 98% POLYURETHANE 2%"
    )
    assert result["status"] == "success", result
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 50, "polyester": 50}
    assert result["parts"] == {
        "outer": {"cotton": 50, "polyester": 50},
        "outer_2": {"nylon": 98, "polyurethane": 2},
    }


@pytest.mark.parametrize("heading", ["面料", "表地"])
def test_unread_first_fabric_cannot_borrow_second_fabrics_composition(heading):
    result = parse_label(f"{heading}1\nUNKNOWN 100%\n{heading}2\nNYLON 100%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("heading", ["面料", "表地"])
@pytest.mark.parametrize("ratio", ["100%", "100 %", "100.0%"])
def test_unnumbered_cjk_heading_keeps_all_percentage_digits(heading, ratio):
    result = parse_label(f"{heading} {ratio}\nCOTTON")
    assert result["status"] == "success", result
    assert result["parts"] == {"outer": {"cotton": 100}}


@pytest.mark.parametrize("heading", ["面料", "表地"])
@pytest.mark.parametrize("suffix", ["2%", "20%", "200%", "2.5%", "2,5%"])
def test_ratio_or_larger_index_is_not_erased_as_a_second_fabric(heading, suffix):
    text = f"{heading} {suffix}\nCOTTON 100%"
    assert declared_part(f"{heading} {suffix}") != "outer_2"
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("heading", ["面料", "表地"])
@pytest.mark.parametrize("suffix", ["21", "200", "2.5", "2,5"])
def test_longer_number_does_not_match_the_second_fabric_alias(heading, suffix):
    marker = f"{heading} {suffix}"
    assert declared_part(marker) != "outer_2"
    assert build_line_infos(marker)[0].normalized == marker


def test_fullwidth_fabric_indices_follow_existing_unicode_normalization():
    result = parse_label("面料１：棉１００％\n面料２：锦纶１００％")
    assert result["status"] == "success", result
    assert result["parts"] == {"outer": {"cotton": 100}, "outer_2": {"nylon": 100}}


def test_second_fabric_marker_does_not_supply_a_missing_percentage():
    infos = build_line_infos("面料2\nCOTTON 98%")
    assert infos[0].numbers == ()
    result = parse_label("面料2\nCOTTON 98%")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


@pytest.mark.parametrize("heading", ["面料2", "表地2"])
@pytest.mark.parametrize("prefix", ["非", "NOT ", "UNKNOWN ", "商品", "品番: "])
def test_embedded_or_negated_numbered_words_cannot_assign_a_part(heading, prefix):
    marker = prefix + heading
    assert declared_part(marker) is None
    result = parse_label(f"{marker}\nCOTTON 100%")
    assert result.get("selected_part") not in {"outer", "outer_2"}


@pytest.mark.parametrize("marker", ["[面料2]", "(表地2)", "CN: 面料2", "JP: 表地2"])
def test_bracketed_and_country_labelled_numbered_headings_are_explicit(marker):
    result = parse_label(f"{marker}\nNYLON 100%")
    assert result["status"] == "success", result
    assert result["parts"] == {"outer_2": {"nylon": 100}}
