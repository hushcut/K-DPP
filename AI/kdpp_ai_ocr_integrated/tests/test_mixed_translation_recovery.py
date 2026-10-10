"""Printed primary declarations stay literal through repeated translations."""

from dataclasses import replace
import re

import pytest

from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


def reading(text, source):
    words = []
    for row, line in enumerate(text.splitlines()):
        x, y = 20, 20 + row * 50
        if line == "☆":
            y -= 50  # Provider paragraph order split one physical footer row.
        for token in re.findall(r"[^\W\d_]+|\d+|[^\w\s]", line):
            width = max(12, len(token) * 12)
            words.append(OcrWord(token, x, y, x + width, y + 24,
                                 ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24))))
            x += width + 4
    return _build_payload_candidates(
        source, OcrPayload(text, layout_words=tuple(words)), image_key="one-image",
        image_variant_key=source + "-input", image_region=(0, 0, 1800, 2000),
        image_transform=(1, 0, 0, 0, 1, 0),
    )[0]


GOOD = ("Composition/\n62% Polyester/Poliéster/ポリエステル/\n"
        "38% Cotton/Coton/Baumwolle/Algodão/E\n30\n☆\nWASH WITH LIKE COLORS")
BAD = GOOD.replace("Algodão/E", "Algodgo/E")


def pair():
    # The spelling changes in a secondary copy; all primary rows/numbers and
    # their coordinates are identical. No material is supplied from the truth.
    return reading(BAD, "preprocessed"), reading(GOOD, "original")


def test_literal_mixed_primary_rows_survive_bounded_translation_damage():
    bad, good = pair()
    assert bad.parser_status == "failed" and good.parser_status == "success"
    assert same_region_recovery(bad, good, "generic", [bad, good])
    result = _assess_candidates([bad, good])
    assert result.status == "success"
    assert result.best.materials == {"polyester": 62, "cotton": 38}
    assert "Algodgo" in bad.text
    assert "damaged_translation_fragment" in good.parser_warnings


@pytest.mark.parametrize("tail", ["UNKNOWN", "OLEFIN", "NYLON", "FAUX LEATHER", "PU", "PA", "CUSTOMFIBER",
                                  "10%", "0.5", "-5", "±", "≈", "abc"])
def test_terminal_translation_glyph_does_not_hide_materials_numbers_or_long_names(tail):
    result = parse_label(GOOD.replace("/E", "/" + tail))
    assert result["status"] == "failed", result


@pytest.mark.parametrize("text", [
    "100% Cotton/Coton/E", "100% Cotton/Coton/Baumwolle/E",
    "100% Cotton/Coton/Baumwolle/Algodão/EE", "70% Cotton/Coton/Baumwolle/Algodão/E",
    "100% Cotton/Coton/Baumwolle/Algodão/E UNKNOWN",
])
def test_terminal_glyph_requires_four_complete_copies_and_complete_composition(text):
    assert parse_label(text)["status"] == "failed"


@pytest.mark.parametrize("between", ["FOO", "OLEFIN", "10%", "0.5", "±"])
def test_temperature_context_cannot_jump_across_opaque_or_numeric_rows(between):
    result = parse_label("100% COTTON\n30\n" + between + "\nHAND WASH")
    assert result["status"] == "failed", result


@pytest.mark.parametrize("text", [
    "100% Cotton-Coton-Algodão", "100% Cotton-Coton-\nAlgodão-Baumwolle-",
    "100% Polyester-Poliéster-ポリエステル",
])
def test_complete_hyphen_translations_keep_primary_ratio_and_readable_copies(text):
    result = parse_label(text)
    assert result["status"] == "success", result
    expected = "cotton" if "Cotton" in text else "polyester"
    assert result["materials"] == {expected: 100}
    assert result["parse_evidence"]["observed_ratios"]["generic"] == [100.0]


@pytest.mark.parametrize("tail", ["UNKNOWN", "OLEFIN", "NYLON", "FAUX", "XNONOK", "2", "$100%-KAPAS",
                                  "100%-KAPAS", "10%", "-5", "+5", "≈", "CUSTOMFIBER"])
def test_hyphen_reader_preserves_unregistered_copies_and_every_extra_number(tail):
    text = "100% Cotton-Coton-Algodão-" + tail
    assert parse_label(text)["status"] == "failed", text


@pytest.mark.parametrize("neighbor", ["FOO", "OLEFIN", "UNKNOWN", "CUSTOMFIBER", "NYLON", "10%", "≈"])
@pytest.mark.parametrize("side", ["before", "after"])
def test_hyphen_lists_do_not_drop_adjacent_opaque_or_additional_evidence(neighbor, side):
    text = "100% Cotton-Coton-Algodão"
    text = f"{neighbor}\n{text}" if side == "before" else f"{text}\n{neighbor}"
    assert parse_label(text)["status"] == "failed"


@pytest.mark.parametrize("code", ["PU", "PA", "PE", "PP", "PES", "PLA", "MIX", "UNK", "NY", "WO", "ELA"])
def test_mixed_recovery_keeps_ambiguous_short_polymer_codes(code):
    bad, good = pair()
    bad = reading(bad.text.replace("Algodgo", code), bad.source)
    assert not same_region_recovery(bad, good, "generic", [bad, good])


@pytest.mark.parametrize("defect", [
    "unknown", "new_fiber", "new_ratio", "changed_ratio", "changed_primary", "long_damage", "opaque_prefix",
    "opaque_before_care", "missing_percent", "missing_box", "missing_polygon", "duplicate_box", "different_page",
    "other_image", "moved_primary", "moved_copy", "outside_region", "no_care", "same_input_other_source",
    "same_source_same_input", "same_source_other_input",
])
def test_mixed_recovery_requires_complete_literal_primary_geometry_and_all_evidence(defect):
    bad, good = pair()
    changes = {
        "unknown": ("Algodgo", "UNKNOWN"), "new_fiber": ("Algodgo", "NYLON"),
        "new_ratio": ("Algodgo", "10%"), "changed_ratio": ("62%", "61%"),
        "changed_primary": ("Polyester/", "Cotton/"), "long_damage": ("Algodgo", "CUSTOMFIBER"),
        "opaque_prefix": ("Composition/", "FOO\nComposition/"),
        "opaque_before_care": ("30\n☆", "30\nFOO"), "no_care": ("WASH WITH LIKE COLORS", "FOO"),
    }
    if defect in changes:
        old, new = changes[defect]
        bad = reading(bad.text.replace(old, new), bad.source)
        if defect == "no_care":
            good = reading(good.text.replace(old, new), good.source)
    elif defect == "other_image":
        bad = replace(bad, image_key="other-image")
    elif defect == "outside_region":
        bad = replace(bad, image_region=(0, 0, 100, 100))
    elif defect == "same_input_other_source":
        bad = replace(bad, image_variant_key=good.image_variant_key)
    elif defect == "same_source_same_input":
        bad = replace(bad, source=good.source, image_variant_key=good.image_variant_key)
    elif defect == "same_source_other_input":
        bad = replace(bad, source=good.source)
    else:
        words = list(bad.image_words)
        index = next(i for i, w in enumerate(words) if w.text == ("Algodgo" if defect == "moved_copy" else "62"))
        if defect == "missing_percent":
            words = [w for w in words if w.text != "%"]
        elif defect == "missing_box":
            words.pop(index)
        elif defect == "duplicate_box":
            words.append(words[index])
        elif defect == "missing_polygon":
            words[index] = replace(words[index], vertices=())
        elif defect == "different_page":
            words[index] = replace(words[index], page=1)
        else:
            w = words[index]
            words[index] = replace(w, left=w.left + 500, right=w.right + 500,
                                   vertices=tuple((x + 500, y) for x, y in w.vertices))
        bad = replace(bad, image_words=tuple(words))
    assert not same_region_recovery(bad, good, "generic", [bad, good])
