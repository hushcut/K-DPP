from apps.text.parse_label import parse_label


def test_simplified_chinese_polyester_composition() -> None:
    result = parse_label("面料：棉 80% 聚酯纤维 20%")

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 80, "polyester": 20}


def test_simplified_chinese_spandex_composition() -> None:
    result = parse_label("面料：棉 80% 氨纶 20%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 80, "spandex": 20}


def test_simplified_chinese_nylon_composition() -> None:
    result = parse_label("锦纶 88% 氨纶 12%")

    assert result["status"] == "success"
    assert result["materials"] == {"nylon": 88, "spandex": 12}


def test_simplified_chinese_viscose_composition() -> None:
    result = parse_label("粘胶纤维 95% 氨纶 5%")

    assert result["status"] == "success"
    assert result["materials"] == {"viscose": 95, "spandex": 5}


def test_traditional_chinese_polyester_composition() -> None:
    result = parse_label("面料：棉 70% 聚酯纖維 30%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 70, "polyester": 30}


def test_traditional_chinese_spandex_composition() -> None:
    result = parse_label("棉 95% 氨綸 5%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 95, "spandex": 5}


def test_chinese_common_lyocell_and_nylon_terms_are_parsed() -> None:
    result = parse_label("表布：天丝 70% 锦纶 30%")

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"lyocell": 70, "nylon": 30}


def test_traditional_chinese_lyocell_and_lining_are_kept_separate() -> None:
    result = parse_label("表布：萊賽爾 100%\n內裡：聚酯纖維 100%")

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"lyocell": 100}
    assert result["parts"] == {
        "outer": {"lyocell": 100},
        "lining": {"polyester": 100},
    }


def test_japanese_basic_composition() -> None:
    result = parse_label("綿 80% ポリエステル 20%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 80, "polyester": 20}


def test_japanese_polyurethane_composition() -> None:
    result = parse_label("ポリエステル 95% ポリウレタン 5%")

    assert result["status"] == "success"
    assert result["materials"] == {"polyester": 95, "polyurethane": 5}


def test_japanese_full_width_digits_and_percent_sign() -> None:
    result = parse_label("綿８０％ ポリエステル２０％")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 80, "polyester": 20}


def test_japanese_outer_and_lining_are_kept_separate() -> None:
    result = parse_label("表地：綿 100%\n裏地：ポリエステル 100%")

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 100}
    assert result["parts"] == {
        "outer": {"cotton": 100},
        "lining": {"polyester": 100},
    }


def test_japanese_common_material_names_and_part_markers_are_parsed() -> None:
    result = parse_label(
        "表素材：コットン 60% リヨセル 40%\n"
        "裏素材：ポリエステル 100%"
    )

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 60, "lyocell": 40}
    assert result["parts"] == {
        "outer": {"cotton": 60, "lyocell": 40},
        "lining": {"polyester": 100},
    }


def test_common_japanese_ocr_typos_are_corrected() -> None:
    result = parse_label("ポリエスデル 95% ナイロソ 5%")

    assert result["status"] == "success"
    assert result["materials"] == {"polyester": 95, "nylon": 5}


def test_japanese_long_vowel_material_names_are_not_split() -> None:
    result = parse_label("組成表示\n表地 モダール 55% レーヨン 45%")

    assert result["status"] == "success"
    assert result["materials"] == {"modal": 55, "rayon": 45}


def test_japanese_label_layout_with_spandex_is_not_normalized_incorrectly() -> None:
    result = parse_label(
        "組成表示\n表地\n55% モダール\n40% 羊毛\n5% スパンデックス\n"
        "裏地\n100% 綿"
    )

    assert result["status"] == "success"
    assert result["materials"] == {"modal": 55, "wool": 40, "spandex": 5}
    assert result["parts"]["lining"] == {"cotton": 100}


def test_chinese_common_part_markers_and_product_numbers_are_separated() -> None:
    result = parse_label(
        "纤维成分\n主面料：亚麻 80% 聚酰胺纤维 20%\n"
        "内衬：蠶絲 100%\n货号 20260914"
    )

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"linen": 80, "nylon": 20}
    assert result["parts"]["lining"] == {"silk": 100}
