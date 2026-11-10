"""A 100 percent declaration is not a numbered part heading."""

import pytest

from apps.text.parse_label import build_line_infos, parse_label, _is_ratio_only_composition_row


@pytest.mark.parametrize("heading", ["겉감", "겉 감", "OUTER", "SHELL", "OUTSHELL"])
@pytest.mark.parametrize("ratio", ["100%", "100 %", "100.0%"])
def test_numbered_alias_does_not_hide_a_complete_percentage(heading, ratio):
    text = f"{heading} {ratio}\nCOTTON"
    infos = build_line_infos(text)
    assert _is_ratio_only_composition_row(infos[0])
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "outer"


@pytest.mark.parametrize("heading,part", [("겉감1", "outer"), ("겉감2", "outer_2"),
                                           ("SHELL 1", "outer"), ("SHELL 2", "outer_2")])
def test_genuine_numbered_headings_keep_their_separate_part(heading, part):
    result = parse_label(f"{heading}: 100%\nNYLON")
    assert result["status"] == "success", result
    assert result["parts"] == {part: {"nylon": 100}}


@pytest.mark.parametrize("text", [
    "OUTER 100%\nUNKNOWN COTTON", "OUTER 100%\nCOTTON\nNYLON",
    "OUTER 100%\nLINING\nCOTTON", "OUTER 101%\nCOTTON",
    "OUTER 1000%\nCOTTON", "OUTER 100%\nCOTTON 50%",
    "OUTER 100% UNKNOWN\nCOTTON", "OUTER 100%\nFAUX LEATHER",
])
def test_uncertain_names_ratios_and_other_part_boundaries_remain_rejected(text):
    result = parse_label(text)
    assert result["status"] == "failed", result
    assert result["materials"] == {}
