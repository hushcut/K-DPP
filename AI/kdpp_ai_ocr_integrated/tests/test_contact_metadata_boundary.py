"""A labelled phone continuation cannot hide composition evidence."""

import pytest

from apps.text.parse_label import _classify_metadata_line, build_line_infos, parse_label


@pytest.mark.parametrize("header", ["고객상담실", "고객 상담실", "소비자상담실", "전화번호", "tel"])
@pytest.mark.parametrize("phone", ["02-123-4567", "02-1 ^ ~~~~ /", "02-1^^~~~/080-123-4567"])
def test_labelled_phone_values_are_metadata_without_repairing_digits(header, phone):
    text = f"겉감: 폴리에스터100%\n{header}: {phone}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"polyester": 100}
    assert phone in result["raw_ocr_preview"]
    row = build_line_infos(text)[-1]
    assert row.is_metadata and not row.numbers


def test_one_continuation_after_a_complete_contact_field_is_supported():
    text = "겉감: 폴리에스터100%\n고객 상담실: 080-123-4567\n02-1 ^ ~~~~ /"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert all(row.is_metadata for row in build_line_infos(text)[-2:])


@pytest.mark.parametrize("row", ["100%", "100", "COTTON 100%", "UNKNOWN 5%",
                                  "02-1 ^ 5%", "02-1 COTTON", "30-70", "0.5%", "UNKNOWN"])
def test_pending_contact_cannot_swallow_material_or_ratio_rows(row):
    assert _classify_metadata_line(row, "contact")[0] is False


@pytest.mark.parametrize("value", ["100%", "UNKNOWN 5%", "02-1 COTTON 100%", "02-1 UNKNOWN",
                                    "02-1?", "30-70", "2-123-4567"])
def test_a_contact_title_does_not_exclude_arbitrary_text(value):
    assert _classify_metadata_line("고객상담실: " + value, None) == (False, None)


def test_unlabelled_damaged_number_remains_invalid_evidence():
    row = build_line_infos("겉감:폴리에스터100%\n02-1 ^ ~~~~ /")[-1]
    assert not row.is_metadata and row.invalid_evidence


def test_pending_contact_expires_after_one_row_and_does_not_cross_a_part():
    lines = build_line_infos("고객상담실:\n02-123-4567\n02-1 ^ ~~~~ /")
    assert lines[1].is_metadata and not lines[2].is_metadata
    lines = build_line_infos("고객상담실:\n안감\n02-1 ^ ~~~~ /")
    assert not lines[-1].is_metadata


def test_phone_metadata_does_not_supply_missing_percentages():
    result = parse_label("겉감: COTTON 90%\n고객상담실:02-123-4567")
    assert result["status"] == "failed" and result["materials"] == {}
