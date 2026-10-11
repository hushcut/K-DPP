"""Assert that fallback results describe one confirmed part, not the whole garment."""


def assert_selected_part(result, part, materials, *, unconfirmed=None):
    assert result["status"] == "success", result
    assert result["selected_part"] == part
    assert result["materials"] == result["parts"][part] == materials
    if unconfirmed:
        assert unconfirmed not in result["parts"]
        assert f"{unconfirmed}:composition_not_confirmed" in result["warnings"]
        assert f"representative_part_fallback:{part}" in result["warnings"]
