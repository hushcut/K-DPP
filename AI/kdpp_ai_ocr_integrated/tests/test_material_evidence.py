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
        "COTTON 1000% POLYESTER 100%",
        "COTTON 92..5% SPANDEX 7.5%",
        "UNKNOWN 60% COTTON 40% POLYESTER",
        "MODACRYLIC 60% COTTON 40% POLYESTER",
        "60% MODACRYLIC 40% COTTON POLYESTER",
        "COTTON 60% MODACRYLIC POLYESTER 40%",
        "60% COTTON MODACRYLIC 40% POLYESTER",
        "COTTON 60% OTHER FIBER POLYESTER 40%",
        "60% COTTON OTHER FIBER 40% POLYESTER",
    ],
)
def test_malformed_or_unmatched_ratio_evidence_is_rejected(text: str) -> None:
    assert_rejected(text)
