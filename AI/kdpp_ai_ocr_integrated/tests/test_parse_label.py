import pytest

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


def test_non_exact_ratio_total_is_not_promoted_to_a_composition() -> None:
    result = parse_label("COTTON 100% POLYURETHANE 5%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


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


def test_excluded_trim_ratio_does_not_invalidate_main_composition() -> None:
    for text in (
        "COTTON 60% POLYESTER 40% (TRIM NYLON 100%)",
        "COTTON 60% POLYESTER 40% TRIM NYLON 100%",
        "면 60% 폴리에스터 40% (장식 나일론 100%)",
    ):
        result = parse_label(text)
        assert result["status"] == "success"
        assert result["materials"] == {"cotton": 60, "polyester": 40}


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


def test_spatially_split_korean_compounds_are_one_material_each() -> None:
    result = parse_label(
        "리오 셀 50%\n나일 론 45%\n폴리 우레탄 5%"
    )

    assert result["status"] == "success"
    assert result["materials"] == {
        "lyocell": 50,
        "nylon": 45,
        "polyurethane": 5,
    }


def test_spatially_split_material_keeps_ratio_order_on_same_line() -> None:
    for text in (
        "면 95% 폴리 우레탄 5%",
        "폴리 우레탄 5% 면 95%",
    ):
        result = parse_label(text)
        assert result["status"] == "success"
        assert result["materials"] == {"cotton": 95, "polyurethane": 5}


def test_complete_multimaterial_candidate_beats_later_standalone_candidate() -> None:
    result = parse_label(
        "리오셀 70%\n나일론 30%\n혼용율 폴리에스터 100%"
    )

    assert result["status"] == "success"
    assert result["materials"] == {"lyocell": 70, "nylon": 30}


def test_incomplete_outer_does_not_promote_lining_to_the_whole_garment() -> None:
    result = parse_label("OUTER COTTON 95%\nLINING NYLON 100%")

    assert result["status"] == "failed"
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == {}
    assert "outer:composition_not_confirmed" in result["warnings"]


def test_unreadable_outer_material_does_not_promote_lining() -> None:
    result = parse_label("겉감: 인조모피\n안감: 폴리에스터 100%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_trailing_part_marker_keeps_each_ratio_with_its_own_part() -> None:
    result = parse_label("100% POLYESTER SHELL\n100% COTTON LINING")

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"polyester": 100}
    assert result["parts"]["lining"] == {"cotton": 100}


def test_wash_temperature_does_not_complete_a_partial_composition() -> None:
    result = parse_label("COTTON 70% SPANDEX 30°C MACHINE WASH")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_leading_materials_summing_to_100_do_not_drop_a_later_one() -> None:
    result = parse_label("COTTON 60%\nPOLYESTER 40%\nSPANDEX 5%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_part_marker_inside_a_longer_word_is_not_a_part() -> None:
    result = parse_label(
        "IMPORTED AND DISTRIBUTED BY ABC\n100% COTTON\nLINING: 100% POLYESTER"
    )

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
    assert result["parts"]["lining"] == {"polyester": 100}


def test_faux_leather_is_not_confirmed_as_leather() -> None:
    for text in ("FAUX LEATHER 100%", "인조 가죽 100%"):
        result = parse_label(text)

        assert result["status"] == "failed"
        assert result["materials"] == {}
        assert "generic:unresolved_material_token" in result["warnings"]


def test_unlisted_fiber_does_not_hand_its_ratio_to_a_neighbour() -> None:
    result = parse_label("MODACRYLIC 60% COTTON 40% POLYESTER")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_unlisted_fiber_in_a_material_column_blocks_the_ratio_column() -> None:
    result = parse_label("COTTON METALLIC POLYESTER\n60% 40%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_garbled_chinese_fiber_name_does_not_become_the_whole_composition() -> None:
    result = parse_label("人造丝 腨纶\n100%")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_chinese_fiber_aliases_are_resolved() -> None:
    result = parse_label("面料:棉 98% 彈性纖維 2%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 98, "spandex": 2}


def test_multilingual_label_repeating_one_composition_is_not_ambiguous() -> None:
    result = parse_label(
        "SHELL : COTTON 98% POLYURETHANE 2%\n"
        "LINING: POLYESTER 80% COTTON 20%\n"
        "面料:棉 98% 氨纶 2%\n"
        "里料:聚酯纤维 80% 棉 20%\n"
        "겉감\n면 98% 폴리우레탄 2%\n"
        "안감 : 폴리에스터 80% 면 20%"
    )

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 98, "polyurethane": 2}
    assert result["parts"]["lining"] == {"polyester": 80, "cotton": 20}


def test_misread_lining_marker_does_not_land_in_the_outer_part() -> None:
    result = parse_label(
        "SHELL : COTTON 98% POLYURETHANE 2%\nUNING: POLYESTER 80% COTTON 20%"
    )

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["materials"] == {"cotton": 98, "polyurethane": 2}
    assert result["parts"]["lining"] == {"polyester": 80, "cotton": 20}


def test_metadata_sharing_a_row_keeps_the_explicit_composition() -> None:
    for text, expected in (
        ("품번 AB1234 면 100%", {"cotton": 100}),
        ("제조국: 베트남 면 95% 폴리우레탄 5%", {"cotton": 95, "polyurethane": 5}),
        ("면 100% 2024년 제조", {"cotton": 100}),
        ("COTTON 100% 95cm", {"cotton": 100}),
    ):
        result = parse_label(text)

        assert result["status"] == "success", text
        assert result["materials"] == expected, text


def test_metadata_row_does_not_rescue_a_partial_or_descriptive_ratio() -> None:
    for text in ("품번 AB1234 면 60%", "SILK TOUCH 100%"):
        result = parse_label(text)

        assert result["status"] == "failed", text
        assert result["materials"] == {}, text


def test_bare_number_beside_care_text_is_not_inferred_as_a_ratio() -> None:
    for text in (
        "COTTON 70% SPANDEX 30 MACHINE WASH",
        "면 70% 스판덱스 30 손세탁",
    ):
        result = parse_label(text)

        assert result["status"] == "failed", text
        assert result["materials"] == {}, text


def test_leading_lining_marker_leaves_the_unlabeled_main_row_alone() -> None:
    for text in ("면 100%\n안감\n폴리에스터 100%", "COTTON 100%\nLINING\nPOLYESTER 100%"):
        result = parse_label(text)

        assert result["status"] == "success", text
        assert result["materials"] == {"cotton": 100}, text
        assert result["parts"] == {
            "generic": {"cotton": 100},
            "lining": {"polyester": 100},
        }, text


def test_outer_marker_owning_no_row_names_the_row_before_it() -> None:
    result = parse_label("면 100% 겉감\n안감\n폴리에스터 100%")

    assert result["status"] == "success"
    assert result["parts"] == {"outer": {"cotton": 100}, "lining": {"polyester": 100}}


def test_stray_non_outer_marker_does_not_claim_the_main_row() -> None:
    result = parse_label("면 100%\n배색\n안감\n폴리에스터 100%")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 100}
    assert result["parts"]["lining"] == {"polyester": 100}


def test_wool_variants_are_resolved() -> None:
    for text, expected in (
        ("80% LAMBSWOOL 20% NYLON", {"wool": 80, "nylon": 20}),
        ("MERINO 100%", {"wool": 100}),
    ):
        result = parse_label(text)

        assert result["status"] == "success", text
        assert result["materials"] == expected, text


def test_common_label_notations_are_parsed() -> None:
    for text, expected in (
        ("면 60%, 폴리에스터 40%", {"cotton": 60, "polyester": 40}),
        ("60% COTTON, 40% POLYESTER", {"cotton": 60, "polyester": 40}),
        ("FABRIC: 100% COTTON", {"cotton": 100}),
        ("ORGANIC COTTON 100%", {"cotton": 100}),
        ("면 100%\n95", {"cotton": 100}),
    ):
        result = parse_label(text)

        assert result["status"] == "success", text
        assert result["materials"] == expected, text


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 70% SPANDEX 30 WASH",
        "COTTON 70% SPANDEX 30 WASHING",
        "COTTON 70% SPANDEX 30 IRON",
        "COTTON 70 SPANDEX 30 WASH",
        "면 70% 스판덱스 30 세탁",
        "면 70% 스판덱스 30 물세탁",
        "棉 70% 氨纶 30 水洗",
        "綿 70% ポリウレタン 30 洗濯",
    ],
)
def test_short_care_terms_do_not_supply_missing_ratios(text: str) -> None:
    result = parse_label(text)

    assert result["status"] == "failed"
    assert result["materials"] == {}


@pytest.mark.parametrize("care", ["WASH 30", "IRON 30", "세탁 30", "水洗 30", "洗濯 30"])
def test_explicit_ratios_remain_valid_beside_short_care_terms(care: str) -> None:
    result = parse_label(f"COTTON 70% SPANDEX 30% {care}")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 70, "spandex": 30}


def test_care_word_inside_product_description_does_not_block_ratio_recovery() -> None:
    result = parse_label("STONEWASH COTTON 95% SPANDEX 5")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 95, "spandex": 5}


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 80%\nPOLYESTER 20%\nOUTER\nNYLON 100%\nLINING",
        "COTTON\n80%\nPOLYESTER\n20%\nOUTER\nNYLON\n100%\nLINING",
        "COTTON\nPOLYESTER\n80%\n20%\nOUTER\nNYLON 100%\nLINING",
        "COTTON 80%\nPOLYESTER\n20%\nOUTER\nNYLON 100%\nLINING",
        "COTTON 80%\nSTYLE AB123\nPOLYESTER 20%\nOUTER\nNYLON 100%\nLINING",
        "COTTON 80%\nPOLYESTER 20%\nOUTER\nLINING\nNYLON 100%",
        "면 80%\n폴리에스터 20%\n겉감\n나일론 100%\n안감",
        "棉 80%\n聚酯纤维 20%\n面料\n尼龙 100%\n里料",
        "綿 80%\nポリエステル 20%\n表地\nナイロン 100%\n裏地",
    ],
)
def test_trailing_marker_owns_the_entire_composition_block(text: str) -> None:
    result = parse_label(text)

    assert result["status"] == "success"
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"cotton": 80, "polyester": 20},
        "lining": {"nylon": 100},
    }


@pytest.mark.parametrize(
    "main", ["COTTON 80%\nPOLYESTER", "MODACRYLIC\nCOTTON\n100%"]
)
def test_incomplete_trailing_outer_block_does_not_promote_lining(main: str) -> None:
    result = parse_label(f"{main}\nOUTER\nNYLON 100%\nLINING")

    assert result["status"] == "failed"
    assert result["materials"] == {}


def test_trailing_marker_does_not_split_an_explicitly_named_block() -> None:
    result = parse_label("OUTER COTTON 80%\nPOLYESTER 20%\nLINING")

    assert result["status"] == "success"
    assert result["parts"] == {"outer": {"cotton": 80, "polyester": 20}}


def test_body_measurements_between_material_and_ratio_are_skipped() -> None:
    result = parse_label(
        "아크릴\n신체치수 가슴둘레\n호칭 95\n95cm\n65%\n레이온\n35%"
    )

    assert result["status"] == "success"
    assert result["materials"] == {"acrylic": 65, "rayon": 35}


@pytest.mark.parametrize("main", ["COTTON 80%", "COTTON", "COTTON 100%\nNYLON 20%"])
def test_unconfirmed_unlabeled_main_does_not_fall_back_to_lining(main: str) -> None:
    result = parse_label(f"{main}\nLINING\nPOLYESTER 100%")

    assert result["status"] == "failed"
    assert result["error_code"] == "incomplete_part_composition"
    assert result["materials"] == {}
    assert "generic:composition_not_confirmed" in result["warnings"]


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 100%\nPOLYESTER 20%",
        "POLYESTER 20%\nCOTTON 100%",
        "COTTON 100%\nPOLYESTER",
        "COTTON 100%\nSTYLE AB123\nPOLYESTER 20%",
        "COTTON\n100%\nPOLYESTER 20%",
        "COTTON 60%\nPOLYESTER 40%\nSPANDEX",
    ],
)
def test_complete_candidate_does_not_hide_unpaired_material_rows(text: str) -> None:
    result = parse_label(text)

    assert result["status"] == "failed"
    assert result["materials"] == {}


@pytest.mark.parametrize(
    "text",
    [
        "MODACRYLIC\nCOTTON\n100%",
        "COTTON 100%\nMODACRYLIC 20%",
        "COTTON\nMETALLIC\n100%",
        "腨纶\n棉\n100%",
        "MODACRYLIC\nLINING\nPOLYESTER 100%",
    ],
)
def test_unlisted_fiber_on_its_own_row_cannot_be_ignored(text: str) -> None:
    result = parse_label(text)

    assert result["status"] == "failed"
    assert result["materials"] == {}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("COTTON 80%\nPOLYESTER 20%", {"cotton": 80, "polyester": 20}),
        ("COTTON 80%\nPOLYESTER\n20%", {"cotton": 80, "polyester": 20}),
        ("COTTON\n80%\nPOLYESTER\n20%", {"cotton": 80, "polyester": 20}),
        ("COTTON\nPOLYESTER\n80%\n20%", {"cotton": 80, "polyester": 20}),
        ("COTTON\nCOMPOSITION\n100%", {"cotton": 100}),
        ("COTTON 100%\nCOTON 100%", {"cotton": 100}),
        ("COTTON 100%\nLINING POLYESTER 20%", {"cotton": 100}),
        ("COTTON 100%\nLINING MODACRYLIC 20%", {"cotton": 100}),
        ("COTTON 100%\nTRIM MODACRYLIC 20%", {"cotton": 100}),
        ("SILK TOUCH 100%\nLINING POLYESTER 100%", {"polyester": 100}),
    ],
)
def test_complete_blocks_and_separate_lower_priority_parts_remain_valid(
    text: str, expected: dict[str, int]
) -> None:
    result = parse_label(text)

    assert result["status"] == "success"
    assert result["materials"] == expected


@pytest.mark.parametrize(
    ("text", "source"),
    [
        ("COTTON 60%\nPOLYESTER 40%", "line_pairs"),
        ("COTTON\n60%\nPOLYESTER 40%", "mixed_lines"),
        ("COTTON\n100", "adjacent_lines"),
    ],
)
def test_candidate_layout_source_is_preserved(text: str, source: str) -> None:
    result = parse_label(text)

    assert result["status"] == "success"
    assert result["parse_evidence"]["source"] == source
