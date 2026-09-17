"""Regression tests for evidence-backed material compositions."""

import pytest

from apps.text.parse_label import parse_label, parse_materials


def assert_rejected(text: str, *, error_code: str = "composition_not_found") -> None:
    result = parse_label(text)

    assert result["status"] == "failed", result
    assert result["error_code"] == error_code
    assert result["materials"] == {}
    assert parse_materials(text) == {}


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 90% POLYESTER 5%",
        "COTTON 100% POLYURETHANE 5%",
        "COTTON 60% POLYESTER 39%",
        "COTTON 61% POLYESTER 40%",
        "COTTON 99.5%",
    ],
)
def test_non_exact_totals_are_not_rescaled(text: str) -> None:
    assert_rejected(text)


@pytest.mark.parametrize(
    ("text", "expected", "expected_korean"),
    [
        (
            "COTTON 92.5% SPANDEX 7.5%",
            {"cotton": 92.5, "spandex": 7.5},
            "면 92.5%, 스판덱스 7.5%",
        ),
        (
            "COTTON 33.34% POLYESTER 33.33% NYLON 33.33%",
            {"cotton": 33.34, "polyester": 33.33, "nylon": 33.33},
            "면 33.34%, 나일론 33.33%, 폴리에스터 33.33%",
        ),
    ],
)
def test_decimal_ratios_are_preserved(
    text: str,
    expected: dict[str, float],
    expected_korean: str,
) -> None:
    result = parse_label(text)

    assert result["status"] == "success"
    assert result["materials"] == expected
    assert result["materials_korean"] == expected_korean
    assert sum(result["materials"].values()) == 100
    assert result["parse_evidence"]["composition_status"] == "confirmed"


@pytest.mark.parametrize(
    "text",
    [
        "면 70% 스판덱스 30도 물세탁",
        "COTTON 70% SPANDEX 30°C MACHINE WASH",
        "COTTON 70% SPANDEX 30°",
        "COTTON 70% SPANDEX 30 C",
        "COTTON 70% SPANDEX 30 DEGREES",
        "COTTON 70% SPANDEX 30 DEG",
        "COTTON 100°C",
    ],
)
def test_washing_temperatures_are_not_material_ratios(text: str) -> None:
    assert_rejected(text)


def test_valid_composition_remains_valid_with_separate_temperature() -> None:
    result = parse_label("COTTON 70% SPANDEX 30%\nMACHINE WASH 30°C")

    assert result["status"] == "success"
    assert result["materials"] == {"cotton": 70, "spandex": 30}


@pytest.mark.parametrize(
    "metadata",
    [
        "SIZE\n100",
        "SIZE: 100",
        "사이즈\n100",
        "호칭: 95-100",
        "SIZE\nXL",
        "수축률 3%",
        "수축률\n3% 이하",
        "SHRINKAGE: 3%",
        "SHRINKAGE RATE\n3%",
        "ＳＩＺＥ：\n１００",
    ],
)
@pytest.mark.parametrize("metadata_first", [False, True])
def test_explicit_metadata_does_not_invalidate_composition(
    metadata, metadata_first
) -> None:
    composition = "COTTON 60% POLYESTER 40%"
    text = f"{metadata}\n{composition}" if metadata_first else f"{composition}\n{metadata}"
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 100%\n100",
        "COTTON 100%\n3%",
        "COTTON 100%\nSIZE\n100%",
        "COTTON 100%\nSIZE\nMODACRYLIC 3%",
        "COTTON 100%\nSIZE\n100\nMODACRYLIC 50%",
        "COTTON 100%\nSIZE\n100\n50%",
        "COTTON 100%\nSIZE\nMADE IN KOREA\n100",
        "COTTON 100%\nSHRINKAGE\nPOLYESTER 3%",
        "COTTON 100%\nSHRINKAGE 3% MODACRYLIC 50%",
        "COTTON 95%\nSIZE\n100",
        "COTTON 97%\nSHRINKAGE 3%",
        "COTTON\nSIZE\n100",
        "COTTON\nSIZE 100\n100%",
        "COTTON\nSHRINKAGE 100%",
        "COTTON\nSHRINKAGE\n100%",
        "OUTER COTTON 95%\nSIZE\n100\nLINING NYLON 100%",
    ],
)
def test_metadata_does_not_hide_or_supply_composition_evidence(text) -> None:
    assert_rejected(text)


def test_metadata_header_does_not_consume_a_garment_part() -> None:
    result = parse_label("SIZE\nLINING NYLON 100%")

    assert result["status"] == "success", result
    assert result["materials"] == {"nylon": 100}
    assert result["selected_part"] == "lining"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("면 60%, 폴리에스터 40%", {"cotton": 60, "polyester": 40}),
        ("60% COTTON, 40% POLYESTER", {"cotton": 60, "polyester": 40}),
        ("FABRIC: 100% COTTON", {"cotton": 100}),
        ("ORGANIC COTTON 100%", {"cotton": 100}),
        ("품번 AB1234 면 100%", {"cotton": 100}),
        (
            "제조국: 베트남 면 95% 폴리우레탄 5%",
            {"cotton": 95, "polyurethane": 5},
        ),
        ("면 100%\n95", {"cotton": 100}),
    ],
)
def test_common_label_formats_from_integration_review(
    text: str,
    expected: dict[str, int],
) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == expected
    assert result["parse_evidence"]["source"] == "same_line"
    assert result["parse_evidence"]["explicit_percent"] is True


@pytest.mark.parametrize("size", ["80", "100", "120", "９５"])
def test_unlabeled_korean_garment_sizes_after_complete_composition(
    size: str,
) -> None:
    result = parse_label(f"면 100%\n{size}")

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["confidence"]["parser"] == "medium"
    assert result["warnings"] == ["unlabeled_garment_size_inferred"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ORGANIC COTTON 100%", {"cotton": 100}),
        ("RECYCLED POLYESTER 100%", {"polyester": 100}),
        ("BODY: COTTON 100%", {"cotton": 100}),
        ("COTTON 100% MADE IN CHINA", {"cotton": 100}),
        ("COTTON 100% RN 12345", {"cotton": 100}),
        (
            "COTTON 60%, POLYESTER 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "COTTON 60, POLYESTER 40",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "COTTON 60 POLYESTER 40 MADE IN CHINA",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "COTTON 60 POLYESTER 40 WASH COLD",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "COTTON 60 POLYESTER 40 RN 12345",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "COTTON 70% VIRGIN WOOL 30%",
            {"cotton": 70, "wool": 30},
        ),
        (
            "POLYESTER 80% VIRGIN WOOL 20%",
            {"polyester": 80, "wool": 20},
        ),
    ],
)
def test_descriptors_punctuation_and_metadata_do_not_invalidate_ratios(
    text: str,
    expected: dict[str, int],
) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == expected


def test_ambiguous_outer_is_not_replaced_by_lining() -> None:
    assert_rejected(
        "OUTER COTTON 100%\nPOLYESTER 100%\nLINING NYLON 100%",
        error_code="ambiguous_composition",
    )


def test_incomplete_outer_is_not_replaced_by_lining() -> None:
    assert_rejected("OUTER COTTON 95%\nLINING NYLON 100%")


def test_unrecognized_outer_is_not_replaced_by_lining() -> None:
    assert_rejected("겉감: 인조모피\n안감: 폴리에스터 100%")


@pytest.mark.parametrize(
    ("text", "expected", "selected_part"),
    [
        (
            "OUTER\nCOTTON 100%\nLINING NYLON 100%",
            {"cotton": 100},
            "outer",
        ),
        (
            "겉감:\n면 100%\n안감: 폴리에스터 100%",
            {"cotton": 100},
            "outer",
        ),
        ("LINING\nNYLON 100%", {"nylon": 100}, "lining"),
        ("OUTER FABRIC\nCOTTON 100%", {"cotton": 100}, "outer"),
        (
            "OUTER: BRUSHED FINISH\nCOTTON 100%\nLINING NYLON 100%",
            {"cotton": 100},
            "outer",
        ),
    ],
)
def test_part_headers_without_composition_remain_supported(
    text: str,
    expected: dict[str, int],
    selected_part: str,
) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == expected
    assert result["selected_part"] == selected_part


@pytest.mark.parametrize(
    "text",
    [
        "FAUX LEATHER 100%",
        "FAUX-LEATHER 100%",
        "FAKE LEATHER 100%",
        "SYNTHETIC LEATHER 100%",
        "ARTIFICIAL LEATHER 100%",
        "IMITATION LEATHER 100%",
        "VEGAN LEATHER 100%",
        "PU LEATHER 100%",
        "PVC LEATHER 100%",
        "PU 가죽 100%",
        "인조 가죽 100%",
        "인조가죽 100%",
        "합성 가죽 100%",
        "모조 가죽 100%",
        "비건 가죽 100%",
        "人造 皮革 100%",
        "人工 皮革 100%",
        "合成 皮革 100%",
        "仿 皮革 100%",
        "フェイク レザー 100%",
        "SIMILI CUIR 100%",
        "KUNST LEDER 100%",
        "FAUX LEATHER\n100%",
    ],
)
def test_faux_leather_is_not_treated_as_natural_leather(text: str) -> None:
    assert_rejected(text)


@pytest.mark.parametrize(
    "text",
    [
        "LEATHER 100%",
        "GENUINE LEATHER 100%",
        "REAL LEATHER 100%",
        "NATURAL LEATHER 100%",
        "PATENT LEATHER 100%",
        "가죽 100%",
        "천연 가죽 100%",
        "皮革 100%",
    ],
)
def test_natural_leather_remains_supported(text: str) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == {"leather": 100}


@pytest.mark.parametrize(
    "text",
    [
        "100% POLYESTER SHELL\n100% COTTON LINING",
        "POLYESTER 100% SHELL\nCOTTON 100% LINING",
        "100% POLYESTER (SHELL)\n100% COTTON (LINING)",
        "100% POLYESTER - SHELL\n100% COTTON - LINING",
        "폴리에스터 100% 겉감\n면 100% 안감",
        "POLYESTER SHELL\n100%\nCOTTON LINING\n100%",
    ],
)
def test_suffix_part_markers_bind_to_preceding_composition(text: str) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 100}
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"polyester": 100},
        "lining": {"cotton": 100},
    }


def test_suffix_part_marker_supports_multi_material_composition() -> None:
    result = parse_label(
        "COTTON 60% POLYESTER 40% SHELL\n"
        "NYLON 100% LINING"
    )

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"cotton": 60, "polyester": 40},
        "lining": {"nylon": 100},
    }


def test_incomplete_suffix_outer_is_not_replaced_by_lining() -> None:
    assert_rejected("COTTON 95% SHELL\nNYLON 100% LINING")


def test_inline_part_transition_remains_supported() -> None:
    result = parse_label(
        "SHELL: 100% POLYESTER LINING: 100% COTTON"
    )

    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 100}
    assert result["selected_part"] == "outer"
    assert result["parts"] == {
        "outer": {"polyester": 100},
        "lining": {"cotton": 100},
    }


@pytest.mark.parametrize(
    "metadata",
    [
        "IMPORTED AND DISTRIBUTED BY ABC",
        "SHELLFISH PRODUCTS",
        "SEASHELL DESIGN",
        "STREAMLINING PROCESS",
        "OUTERWEAR COLLECTION",
        "FACELIFT COLLECTION",
        "REFILLABLE PRODUCT",
        "POCKETBOOK STYLE",
        "SLEEVELESS TOP",
        "CONTRASTING COLOR",
        "SURFACE TREATMENT",
        "INTERFACE DESIGN",
        "DESCRIBED STYLE",
        "RIBBON DETAIL",
        "MAIN FABRICATION LINE",
    ],
)
def test_part_marker_aliases_are_matched_as_tokens(metadata: str) -> None:
    result = parse_label(
        f"{metadata}\n"
        "100% COTTON\n"
        "LINING: 100% POLYESTER"
    )

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "generic"
    assert result["parts"] == {
        "generic": {"cotton": 100},
        "lining": {"polyester": 100},
    }


@pytest.mark.parametrize(
    ("text", "materials", "part"),
    [
        ("COTTON 100% RIB", {"cotton": 100}, "rib"),
        ("MAIN   FABRIC: COTTON 100%", {"cotton": 100}, "outer"),
        ("겉 감: 면 100%", {"cotton": 100}, "outer"),
        ("本体: 綿 100%", {"cotton": 100}, "outer"),
        ("面料: 棉 100%", {"cotton": 100}, "outer"),
        ("裏地ポリエステル 100%", {"polyester": 100}, "lining"),
    ],
)
def test_part_markers_remain_supported(
    text: str,
    materials: dict[str, int],
    part: str,
) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == materials
    assert result["selected_part"] == part


def test_explicit_rib_part_remains_supported() -> None:
    result = parse_label("RIB: COTTON 100%")

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "rib"


@pytest.mark.parametrize(
    "text",
    [
        "COTTON 100%\nMODACRYLIC 50%",
        "COTTON 100%\nPOLYESTER 50%",
        "COTTON 100%\nPOLYESTER 50% SPANDEX 50%",
    ],
)
def test_unresolved_or_conflicting_evidence_in_same_part_blocks_success(
    text: str,
) -> None:
    error_code = (
        "ambiguous_composition" if "SPANDEX" in text else "composition_not_found"
    )
    assert_rejected(text, error_code=error_code)


def test_equivalent_multilingual_compositions_are_corroborating_evidence() -> None:
    result = parse_label(
        "COTTON 60% POLYESTER 40%\n면 60% 폴리에스터 40%"
    )

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("COTTON / COTON 100%", {"cotton": 100}),
        ("면 / COTTON 100%", {"cotton": 100}),
        ("COTTON (면) 100%", {"cotton": 100}),
        ("COTTON / COTON / 綿 100%", {"cotton": 100}),
        ("100% COTTON / COTON", {"cotton": 100}),
        (
            "COTTON / 면 60% POLYESTER / 폴리에스터 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "60% COTTON / 면 40% POLYESTER / 폴리에스터",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "POLYESTER 80% VIRGIN WOOL / 양모 20%",
            {"polyester": 80, "wool": 20},
        ),
        (
            "면 / COTTON 92.5% SPANDEX / ELASTANE 7.5%",
            {"cotton": 92.5, "spandex": 7.5},
        ),
    ],
)
def test_adjacent_aliases_share_one_ratio(text, expected) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == expected
    assert parse_materials(text) == expected
    assert result["parse_evidence"]["composition_status"] == "confirmed"


@pytest.mark.parametrize(
    "text",
    [
        "COTTON / POLYESTER 100%",
        "COTTON / MODACRYLIC / COTON 100%",
        "COTTON 100% COTON 10%",
        "COTTON / COTON 60% POLYESTER 40% COTON",
        "COTTON / POLYESTER 60% NYLON 40%",
        "COTTON / COTON 60% MODACRYLIC POLYESTER 40%",
        "COTTON / 면 100% / POLYESTER",
    ],
)
def test_alias_groups_do_not_hide_unmatched_materials_or_ratios(text) -> None:
    assert_rejected(text)


@pytest.mark.parametrize(
    "text",
    [
        "COTTON -60% POLYESTER 40%",
        "COTTON 92, 5% SPANDEX 95%",
        "60%, 40% COTTON POLYESTER",
        "60% COTTON,, 40% POLYESTER",
        "COTTON 1000% POLYESTER 100%",
        "COTTON 92..5% SPANDEX 7.5%",
        "UNKNOWN 60% COTTON 40% POLYESTER",
        "MODACRYLIC 60% COTTON 40% POLYESTER",
        "60% MODACRYLIC 40% COTTON POLYESTER",
        "COTTON 60% MODACRYLIC POLYESTER 40%",
        "60% COTTON MODACRYLIC 40% POLYESTER",
        "COTTON 60% OTHER FIBER POLYESTER 40%",
        "60% COTTON OTHER FIBER 40% POLYESTER",
        "COTTON METALLIC POLYESTER\n60% 40%",
        "COTTON OTHER FIBER POLYESTER\n60% 40%",
        "COTTON UNKNOWN POLYESTER\n60% 40%",
        "COTTON MODACRYLIC POLYESTER\n60% 40%",
        "60% COTTON METALLIC, 40% POLYESTER",
        "60% COTTON, 40% METALLIC POLYESTER",
        "FABRIC WIDTH: 100% COTTON",
        "NON FABRIC: 100% COTTON",
        "FABRICATION: 100% COTTON",
        "FABRIC: 100% UNKNOWN COTTON",
    ],
)
def test_malformed_or_unmatched_ratio_evidence_is_rejected(text: str) -> None:
    assert_rejected(text)


def test_ratio_first_decimal_commas_and_item_separator_are_supported() -> None:
    result = parse_label("92,5% COTTON, 7,5% SPANDEX")

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 92.5, "spandex": 7.5}


@pytest.mark.parametrize(
    "text",
    [
        "면 60%\n95",
        "면 100%\n79",
        "면 100%\n81",
        "면 100%\n125",
        "면 100%\n95%",
        "면 100\n95",
        "COTTON 100%\n95",
        "면 100%\n95\n폴리에스터 5%",
        "면 100%\n95\n40%",
        "면 100%\n95\nMADE IN KOREA",
        "면\n95",
    ],
)
def test_unlabeled_size_inference_does_not_hide_ratio_evidence(text: str) -> None:
    assert_rejected(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "COTTON POLYESTER\n60% 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "ORGANIC COTTON RECYCLED POLYESTER\n60% 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "MATERIAL: COTTON POLYESTER\n60% 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "면 폴리에스터\n60% 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "COTTON / COTON POLYESTER / 폴리에스터\n60% 40%",
            {"cotton": 60, "polyester": 40},
        ),
        (
            "면 및 폴리에스터\n60% 40%",
            {"cotton": 60, "polyester": 40},
        ),
    ],
)
def test_stacked_materials_and_ratios_remain_supported(
    text: str,
    expected: dict[str, int],
) -> None:
    result = parse_label(text)

    assert result["status"] == "success", result
    assert result["materials"] == expected
    assert result["parse_evidence"]["source"] == "stacked_columns"


def test_described_alternating_materials_and_ratios_remain_supported() -> None:
    result = parse_label(
        "ORGANIC COTTON\n60%\nRECYCLED POLYESTER\n40%"
    )

    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 60, "polyester": 40}
    assert result["parse_evidence"]["source"] == "alternating_lines"
