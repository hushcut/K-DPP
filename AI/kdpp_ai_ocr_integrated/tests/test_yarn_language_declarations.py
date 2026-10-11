"""Country copies do not multiply a yarn's ratio or overwrite unreadable text."""
import pytest

from apps.text.material_extraction import extract_materials
from apps.text.parse_label import parse_label
from apps.text.scoped_materials import read_yarn_materials
from apps.service.label_analysis import analyze_ocr_result
from apps.text.ocr_text import OcrResult, OcrMetadata
from apps.text.ocr_candidates import build_candidate, literal_yarn_table_over_failed_layout
from apps.text.ocr_layout import OcrWord
from dataclasses import replace


PREFIX = "BRODERI\nYARN/FIL/GARN\n"
AGREED = "UK: 100% POLYESTER FR: 100% POLYESTER KR: 100% 폴리에스터"


@pytest.mark.parametrize("alias", ["POLIESTERE", "POLYESTERI", "POLIESTERIS", "POLÜESTER"])
def test_registered_european_fiber_names_are_complete_tokens(alias):
    assert parse_label(f"100% {alias}")["materials"] == {"polyester": 100}
    assert "polyester" not in extract_materials(alias + "PLUS")


def test_country_copies_keep_a_single_literal_yarn_declaration():
    result = parse_label(PREFIX + AGREED + " IT: 100% POLIESTERE FI: 100% POLYESTERI")
    assert result["status"] == "success"
    assert result["selected_part"] == "embroidery_yarn"
    assert result["materials"] == {"polyester": 100}
    assert result["parse_evidence"]["scoped_materials"]["status"] == "observed"
    assert result["parse_evidence"]["yarn_language_selection"]["language"] == "KR"


def test_unreadable_foreign_copy_is_retained_without_assigning_it_a_fiber():
    text = PREFIX + AGREED + " JP: 100% 刹工下亍元"
    result = parse_label(text)
    assert result["status"] == "success"
    assert result["materials"] == {"polyester": 100}
    assert result["confidence"]["parser"] == "medium"
    evidence = result["parse_evidence"]["scoped_materials"]
    assert evidence["status"] == "partial"
    assert evidence["unconfirmed_clauses"] == [{"language": "JP", "text": "100% 刹工下亍元"}]
    assert "unconfirmed_foreign_yarn_translations" in result["warnings"]
    assert "刹工下亍元" in result["raw_ocr_preview"]


@pytest.mark.parametrize("clause", [
    "JP: 95% 刹工下亍元", "JP: 100% 刹工下亍元 5%", "JP: +100% 刹工下亍元",
    "JP: 100% UNKNOWN", "JP: 100% OLEFIN", "JP: 100% 未登録素材",
    "JP: 100% 未読", "JP: 100% 刹工下亍元 OLEFIN", "JP: 100% 刹工下亍元 &",
    "JP: 100% ナイロン", "JP: 100% 刹工下亍元 綿", "IT: 100% UNREGISTEREDFIBER",
    "CN: 100% 聚酯纤维 未知纤维", "KR: 100% 未知纤维",
])
def test_unknown_extra_and_conflicting_composition_cannot_be_hidden(clause):
    result = parse_label(PREFIX + AGREED + " " + clause)
    assert result["status"] == "failed"
    assert result["materials"] == {}


@pytest.mark.parametrize("agreements", [
    "UK: 100% POLYESTER FR: 100% POLYESTER",
    "FR: 100% POLYESTER DE: 100% POLYESTER KR: 100% 폴리에스터",
    "UK: 100% POLYESTER KR: 100% 폴리에스터",
])
def test_partial_foreign_fallback_needs_literal_korean_english_and_third_language(agreements):
    assert parse_label(PREFIX + agreements + " JP: 100% 刹工下亍元")["status"] == "failed"


@pytest.mark.parametrize("extra", ["UNKNOWN 5%", "COTTON 100%", "OUTER UNKNOWN", "폴리에스터 95%",
    "UNKNOWN", "OLEFIN", "FAUX", "FOO BAR", "UNKNOWN/GARN", "OLEFIN/FIL"])
def test_evidence_between_scope_heading_and_language_table_is_not_discarded(extra):
    assert parse_label(PREFIX + extra + "\n" + AGREED)["status"] == "failed"


@pytest.mark.parametrize("language,alias", [
    ("EL", "ПOAYEZTEPA"), ("EL", "ПOAYEΣTEPAZ"), ("RU", "ПолизстЕР"),
])
def test_script_confusables_require_the_registered_country_and_full_name(language, alias):
    observation = read_yarn_materials(PREFIX + f"UK: 100% POLYESTER {language}: 100% {alias}")
    assert observation["status"] == "observed"
    wrong_scope = read_yarn_materials(PREFIX + f"UK: 100% POLYESTER IT: 100% {alias}")
    assert wrong_scope["status"] == "partial"
    wrong_name = read_yarn_materials(PREFIX + f"UK: 100% POLYESTER {language}: 100% {alias}X")
    assert wrong_name["status"] == "partial"


def test_selected_language_basis_survives_ocr_metadata_merge():
    text = PREFIX + AGREED + " JP: 100% 刹工下亍元"
    result = analyze_ocr_result(OcrResult(text, OcrMetadata(source="original", confidence="medium",
        candidate_count=1, image_format="JPEG", width=800, height=1000,
        scoped_materials=read_yarn_materials(text))))
    assert result["status"] == "success"
    assert result["parse_evidence"]["yarn_language_selection"]["language"] == "KR"
    assert result["parse_evidence"]["scoped_materials"]["unconfirmed_clauses"]


def paired_views():
    text = PREFIX + AGREED
    words = tuple(OcrWord(token, x * 45, y * 35, x * 45 + 40, y * 35 + 20)
        for y, row in enumerate(text.splitlines()) for x, token in enumerate(row.split()))
    raw = replace(build_candidate("original", text, parse_candidate=parse_label),
        image_key="photo", image_variant_key="input", image_words=words, image_region=(0, 0, 700, 200))
    # The coordinate grouping preserved every annotation but broke country
    # clauses into an unusable sequence. It has no successful composition.
    layout = replace(raw, layout_used=True, parser_status="failed", parts={},
        materials={}, text="\n".join(reversed(text.splitlines())))
    return raw, layout


def test_failed_generated_layout_does_not_overrule_the_literal_provider_language_table():
    raw, layout = paired_views()
    assert literal_yarn_table_over_failed_layout(raw, layout)


@pytest.mark.parametrize("defect", [
    "different_image", "different_variant", "different_source", "missing_word",
    "changed_word", "missing_region", "outside_region", "second_page",
    "successful_conflict", "unproven_composition", "changed_digit", "unknown_raw_clause",
])
def test_language_layout_recovery_cannot_drop_missing_or_changed_provider_evidence(defect):
    raw, layout = paired_views()
    if defect == "different_image":
        layout = replace(layout, image_key="another-photo")
    elif defect == "different_variant":
        layout = replace(layout, image_variant_key="another-input")
    elif defect == "different_source":
        layout = replace(layout, source="material_crop")
    elif defect == "missing_word":
        raw = replace(raw, image_words=raw.image_words[:-1])
        layout = replace(layout, image_words=raw.image_words)
    elif defect == "changed_word":
        layout = replace(layout, text=layout.text.replace("POLYESTER", "OLEFIN", 1))
    elif defect == "missing_region":
        raw = replace(raw, image_region=())
        layout = replace(layout, image_region=())
    elif defect == "outside_region":
        raw = replace(raw, image_words=(replace(raw.image_words[0], left=-100),) + raw.image_words[1:])
        layout = replace(layout, image_words=raw.image_words)
    elif defect == "second_page":
        raw = replace(raw, image_words=(replace(raw.image_words[0], page=1),) + raw.image_words[1:])
        layout = replace(layout, image_words=raw.image_words)
    elif defect == "successful_conflict":
        layout = replace(layout, parser_status="success", parts={"embroidery_yarn": {"cotton": 100}})
    elif defect == "unproven_composition":
        layout = replace(layout, conflicting_parts=("embroidery_yarn",))
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("100", "95", 1))
    elif defect == "unknown_raw_clause":
        raw = replace(raw, text=raw.text + " JP: 100% 未登録素材")
    assert not literal_yarn_table_over_failed_layout(raw, layout)
