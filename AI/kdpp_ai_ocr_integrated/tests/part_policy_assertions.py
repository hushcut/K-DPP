"""Assert that fallback results describe one confirmed part, not the whole garment."""


def assert_unconfirmed_outer(result, confirmed_parts):
    assert result["status"] == "failed", result
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == result["parts"] == {}
    assert result["parse_evidence"]["unconfirmed_outer_parts"] == ["outer"]
    assert result["parse_evidence"]["confirmed_parts"] == confirmed_parts
    assert "outer:composition_not_confirmed" in result["warnings"]


def assert_selected_part(result, part, materials, *, unconfirmed=None):
    assert result["status"] == "success", result
    assert result["selected_part"] == part
    assert result["materials"] == result["parts"][part] == materials
    if unconfirmed:
        assert unconfirmed not in result["parts"]
        assert f"{unconfirmed}:composition_not_confirmed" in result["warnings"]
        assert f"representative_part_fallback:{part}" in result["warnings"]
