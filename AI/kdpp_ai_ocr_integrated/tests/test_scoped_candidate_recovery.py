"""Recovered declarations still need complete, co-located provider evidence."""

from dataclasses import replace
import re

import pytest

from apps.text.ocr_corrections import (
    _annotation_tokens, _bounded_composition_context, _covers_row_tokens,
    _repeated_translation_recovery, _shared_percent_recovery, same_region_recovery,
)
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def word(text, x, y, width=None):
    width = width or max(10, len(text) * 12)
    return OcrWord(text, x, y, x + width, y + 24,
                   ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24)))


def reading(text, source, words=None):
    if words is None:
        words = []
        for index, line in enumerate(text.splitlines()):
            x = 20
            for token in re.findall(r"[^\W\d_]+|\d+|[^\w\s]", line):
                item = word(token, x, 20 + 50 * index)
                words.append(item)
                x = item.right + 4
    return _build_payload_candidates(
        source, OcrPayload(text, layout_words=tuple(words)), image_key="one-image",
        image_variant_key=source + "-input", image_region=(0, 0, 1500, 2000),
        image_transform=(1, 0, 0, 0, 1, 0),
    )[0]


def percent_readings():
    old_words = (word("Cotton", 20, 120), word("9596", 180, 120, 64),
                 word("Span", 20, 170), word("596", 180, 170, 48))
    target_words = (word("Cotton", 20, 120), word("95", 180, 120, 28), word("%", 210, 120, 32),
                    word("Span", 20, 170), word("5", 180, 170, 16), word("%", 198, 170, 28))
    header = (word("Designed", 20, 20), word("in", 124, 20), word("Seoul", 152, 20),
              word("Made", 20, 70), word("in", 72, 70), word("Korea", 100, 70))
    care = (word("Machine", 20, 220), word("Wash", 108, 220), word("Cold", 160, 220),
            word("Logo", 20, 300))
    original = reading("Designed in Seoul\nMade in Korea\nCotton 9596\nSpan 596\nMachine Wash Cold\nLogo",
                       "original", header + old_words + care)
    clean = "Cotton 95%\nSpan 5%"
    first = reading(clean, "material_crop", target_words)
    second = reading(clean, "material_crop_rotated", target_words)
    return original, first, second


def test_literal_metadata_fences_release_corresponding_percent_rereads():
    original, first, second = percent_readings()
    assert _bounded_composition_context(original).text == "Cotton 9596\nSpan 596"
    assert _assess_candidates([original, first, second]).status == "success"
    assert _assess_candidates([original, first]).status == "failed"
    assert "Logo" in original.text


@pytest.mark.parametrize("extra,position", [
    (extra, "inside") for extra in ("UNKNOWN", "OLEFIN", "FAUX", "ZORBEX", "Cotton 1%", "11%")
] + [(extra, "after_care") for extra in ("UNKNOWN", "OLEFIN", "FAUX", "ZORBEX 10%", "Cotton 1%", "11%")])
def test_fences_do_not_hide_additional_materials_ratios_or_adjacent_opaque_text(extra, position):
    original, first, second = percent_readings()
    if position == "inside":
        text = original.text.replace("Machine Wash Cold", extra + "\nMachine Wash Cold")
    else:
        text = original.text.replace("Logo", extra)
    # Preserve complete boxes for the extra row. Unlocated extra text also
    # fails, but that is not a sufficient negative control for the fence.
    words = tuple(item for item in original.image_words if item.text != "Logo")
    extra_words = reading(extra, "extra").image_words
    extra_words = tuple(replace(item, top=260, bottom=284,
                               vertices=tuple((x, y + 240) for x, y in item.vertices)) for item in extra_words)
    original = reading(text.replace("\nLogo", ""), original.source, words + extra_words)
    assert _assess_candidates([original, first, second]).status == "failed"


def shared_readings():
    prefix = "Gum\nMade in Korea\nDRY CLEANING\nONLY\n"
    body = "polyester 95\nspan 5\n%"
    words = reading(prefix + body, "original").image_words
    original = reading(prefix + body, "original", words)
    crop = reading("ONLY\n" + body, "material_crop", tuple(item for item in words if item.top >= 170))
    # The parser can reject a truncated caption even when all the declaration
    # boxes are literal. Test the correction proof independently of captions.
    crop = replace(crop, parser_status="failed", rejected_composition_parts={"generic": ("unpaired_material_rows",)})
    assert original.parser_status == "success"
    return crop, original


def test_shared_percent_preserves_two_literal_rows_and_the_one_original_percent_box():
    crop, original = shared_readings()
    assert _shared_percent_recovery(crop, original, "generic", "generic")
    assert _assess_candidates([crop, original]).status == "success"
    assert sum(item.text == "%" for item in crop.image_words) == 1


@pytest.mark.parametrize("defect", ["missing_percent", "wrong_ratio", "shifted_number", "different_image",
                                   "different_page", "missing_polygon", "duplicate_percent", "extra_ratio",
                                   "same_input", "outside_region", "side_percent"])
def test_shared_percent_recovery_requires_literal_numbers_complete_geometry_and_provenance(defect):
    crop, original = shared_readings()
    if defect == "different_image":
        original = replace(original, image_key="other-image")
    elif defect == "same_input":
        original = replace(original, image_variant_key=crop.image_variant_key)
    elif defect == "outside_region":
        crop = replace(crop, image_region=(0, 0, 100, 100))
    else:
        words = list(crop.image_words)
        if defect == "missing_percent":
            words = [item for item in words if item.text != "%"]
        elif defect == "duplicate_percent":
            words.append(next(item for item in words if item.text == "%"))
        elif defect == "extra_ratio":
            words.append(word("10%", 250, 400))
        else:
            index = next(i for i, item in enumerate(words) if item.text == ("%" if defect == "side_percent" else "95"))
            if defect == "wrong_ratio":
                words[index] = replace(words[index], text="94")
            elif defect == "different_page":
                words[index] = replace(words[index], page=1)
            elif defect == "missing_polygon":
                words[index] = replace(words[index], vertices=())
            else:
                old = words[index]
                words[index] = replace(old, left=old.left + 400, right=old.right + 400,
                                       vertices=tuple((x + 400, y) for x, y in old.vertices))
        crop = replace(crop, image_words=tuple(words))
    assert not same_region_recovery(crop, original, "generic", [crop, original])


def translation_readings():
    heading = "Composition/ Zusamme\nnsetzung/ Composición/\n구성:\n"
    good_text = heading + "100% Cotton/ Coton/ Ba\numwolle/ Algodón/ Algo\ndao/all/コットン/"
    bad_text = heading + "100% Cotton/ Coton/ Ba\numwolle/ Algodón/ Algo\ndaof aaly/コットン/"
    return reading(bad_text, "original"), reading(good_text, "material_crop")


def test_coordinate_agreement_recovers_damaged_repeat_copies_without_replacing_primary_text():
    bad, good = translation_readings()
    assert bad.parser_status == "failed" and good.parser_status == "success"
    assert _repeated_translation_recovery(bad, good, "generic", "generic", [bad, good])
    decision = _assess_candidates([bad, good])
    assert decision.status == "success" and decision.best.materials == {"cotton": 100}
    assert "aaly" in bad.text


@pytest.mark.parametrize("defect", ["extra_ratio", "other_material", "unknown", "negation", "long_noise",
                                   "primary_changed", "unboxed_text", "missing_primary_box", "same_input",
                                   "other_image", "other_page", "moved_primary", "moved_foreign_copy"])
def test_translation_repeat_recovery_cannot_erase_new_fibers_or_change_primary_declarations(defect):
    bad, good = translation_readings()
    replacements = {"extra_ratio": ("aaly", "10%"), "other_material": ("aaly", "rayon"),
                    "unknown": ("aaly", "UNKNOWN"), "negation": ("aaly", "FAUX"),
                    "long_noise": ("aaly", "NOVELFIBER"), "primary_changed": ("100%", "90%")}
    if defect in replacements:
        old, new = replacements[defect]
        bad = reading(bad.text.replace(old, new), bad.source)
    elif defect == "unboxed_text":
        bad = replace(bad, text=bad.text.replace("aaly", "UNKNOWN"))
    elif defect == "same_input":
        good = replace(good, image_variant_key=bad.image_variant_key)
    elif defect == "other_image":
        good = replace(good, image_key="other-image")
    else:
        words = list(bad.image_words)
        index = next(i for i, item in enumerate(words) if item.text == ("aaly" if defect == "moved_foreign_copy" else "100"))
        if defect == "missing_primary_box":
            words.pop(index)
        elif defect == "other_page":
            words[index] = replace(words[index], page=1)
        else:
            old = words[index]
            words[index] = replace(old, left=old.left + 600, right=old.right + 600,
                                   vertices=tuple((x + 600, y) for x, y in old.vertices))
        bad = replace(bad, image_words=tuple(words))
    assert not same_region_recovery(bad, good, "generic", [bad, good])


def test_mixed_ascii_and_han_annotations_preserve_complete_runs_and_missing_characters():
    boxes = [word("Example", 20, 20), word("中国", 120, 20)]
    assert _covers_row_tokens(_annotation_tokens("Example中国"), boxes, tokenise=_annotation_tokens)
    assert not _covers_row_tokens(_annotation_tokens("Example中国X"), boxes, tokenise=_annotation_tokens)
