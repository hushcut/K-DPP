from apps.text.parse_label import parse_label


def test_same_line_composition_is_parsed() -> None:
    result = parse_label("COTTON 80% POLYESTER 20%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 80, "polyester": 20}
    assert result["confidence"]["parser"] == "high"


def test_alternating_material_and_ratio_lines_are_paired() -> None:
    result = parse_label("COTTON\n80%\nPOLYESTER\n20%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 80, "polyester": 20}
    assert result["parse_evidence"]["source"] == "alternating_lines"


def test_stacked_material_and_ratio_columns_are_paired() -> None:
    result = parse_label("OUTER\nPOLYESTER\nPOLYURETHANE\n94%\n6%")

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"polyester": 94, "polyurethane": 6}
    assert result["parse_evidence"]["source"] == "stacked_columns"


def test_low_ratio_total_is_not_fabricated() -> None:
    result = parse_label("COTTON 30%")

    assert result["status"] == "failed"
    assert result["error_code"] == "composition_not_found"
    assert result["materials"] == {}


def test_missing_ratio_is_not_fabricated() -> None:
    result = parse_label("COTTON\nPOLYESTER 20%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_korean_poly_abbreviation_is_parsed_as_complete_token() -> None:
    result = parse_label("면 60% 폴리 40%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 60, "polyester": 40}
    assert result["confidence"]["parser"] == "high"


def test_korean_poly_abbreviation_does_not_override_polyurethane() -> None:
    result = parse_label("면 95% 폴리우레탄 5%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 95, "polyurethane": 5}


def test_one_missing_percent_marker_is_recovered_in_composition() -> None:
    result = parse_label("면 95% 스판덱스 5")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 95, "spandex": 5}
    assert result["confidence"]["parser"] == "medium"
    assert result["warnings"] == ["generic:ratio_marker_inferred"]


def test_washing_temperature_is_not_used_as_missing_ratio() -> None:
    result = parse_label("면 95% 스판덱스 30도 물세탁")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_care_only_korean_text_does_not_infer_composition() -> None:
    result = parse_label("드라이클리닝 만 가능 100%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_care_only_english_text_does_not_infer_silk() -> None:
    result = parse_label("Silky touch. Dry clean only.")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_unknown_material_is_not_replaced_with_cotton() -> None:
    result = parse_label("섬유의 조성 ACETATE 100%")

    assert result["status"] == "success"
    assert result["materials"] == {"acetate": 100}


def test_lining_wash_temperature_is_not_used_as_composition() -> None:
    result = parse_label("안감 폴리에스터 / 30도 물세탁")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_equal_rank_conflicting_compositions_are_ambiguous() -> None:
    result = parse_label("COTTON 100%\nPOLYESTER 100%")

    assert result["status"] == "failed"
    assert result["error_code"] == "ambiguous_composition"
    assert result["materials"] == {}


def test_small_ratio_total_error_is_normalized_with_warning() -> None:
    result = parse_label("COTTON 100% POLYURETHANE 5%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 95.2, "polyurethane": 4.8}
    assert result["warnings"] == ["generic:ratio_total_normalized:105.0"]


def test_multilingual_alias_is_not_confused_with_wool() -> None:
    result = parse_label("BAUMWOLLE 100%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}


def test_decoration_composition_does_not_replace_outer_material() -> None:
    result = parse_label(
        "OUTER COTTON 100%\n"
        "EXCLUSIVE OF DECORATION\n"
        "DECORATION ACRYLIC 100%"
    )

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 100}


def test_negative_care_rule_wins_over_general_rule() -> None:
    result = parse_label(
        "COTTON 100%\n"
        "DO NOT BLEACH\n"
        "MACHINE WASH COLD\n"
        "DO NOT TUMBLE DRY"
    )

    assert result["status"] == "success"
    assert "표백 금지" in result["care_instructions"]
    assert "건조기 사용 금지" in result["care_instructions"]
    assert "찬물 기계세탁" in result["care_instructions"]
    assert "건조기 사용" not in result["care_instructions"]

