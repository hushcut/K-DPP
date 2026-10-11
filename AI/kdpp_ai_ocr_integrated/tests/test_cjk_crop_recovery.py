"""A registered Han alias may span boxes, but crop proof must retain every component."""

from dataclasses import replace

import pytest

from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


NAMES = ("聚酯纤维", "人造丝", "氨纶")


def _word(text, x, y, width, height=24):
    vertices = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return OcrWord(text, x, y, x + width, y + height, vertices)


def _name_fragments(name, boxes):
    if boxes == "whole":
        return (name,)
    if boxes == "chars":
        return tuple(name)
    return (name[:-2], name[-2:]) if len(name) > 2 else tuple(name)


def _render_name(name, form):
    fragments = _name_fragments(name, "two")
    return {"joined": "", "spaces": " ", "newline": "\n"}[form].join(fragments)


def _reading(number="5", *, boxes="whole", form="joined", names=NAMES,
             source="original", variant="original-input", layout=""):
    words = []
    rows = []
    for name, value, y in zip(names, (number, "21", "4"), (100, 180, 260), strict=True):
        offset = 0
        for fragment in _name_fragments(name, boxes):
            words.append(_word(fragment, 120 + offset * 40, y, len(fragment) * 40))
            offset += len(fragment)
        words.extend((_word(value, 500, y, 60), _word("%", 565, y, 20)))
        rows.append(_render_name(name, form) + " " + value + "%")
    return _build_payload_candidates(
        source, OcrPayload("\n".join(rows), layout_text=layout, layout_words=tuple(words)),
        image_key="one-label", image_variant_key=variant,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(80, 70, 650, 320),
    )


def _pair(*, number="5", source_boxes="whole", source_form="joined",
          target_boxes="two", target_form="joined", names=NAMES):
    original = _reading(number, boxes=source_boxes, form=source_form, names=names)
    crop = _reading("75", boxes=target_boxes, form=target_form, names=names,
                    source="material_crop", variant="actual-crop-input")
    assert original[0].parser_status == "failed"
    assert crop[0].parser_status == "success"
    return original, crop


def _rebuild(candidate, *, text=None, words=None):
    return _build_payload_candidates(
        candidate.source,
        OcrPayload(candidate.text if text is None else text,
                   layout_words=candidate.image_words if words is None else words),
        image_key=candidate.image_key, image_variant_key=candidate.image_variant_key,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=candidate.image_region,
    )[0]


@pytest.mark.parametrize("source_boxes,source_form,target_boxes,target_form", [
    ("whole", "joined", "two", "joined"),
    ("two", "joined", "whole", "joined"),
    ("two", "spaces", "chars", "joined"),
    ("chars", "newline", "two", "spaces"),
    ("chars", "joined", "chars", "newline"),
    ("whole", "spaces", "whole", "spaces"),
])
def test_complete_registered_han_rows_recover_one_observed_missing_digit(
    source_boxes, source_form, target_boxes, target_form,
):
    original, crop = _pair(source_boxes=source_boxes, source_form=source_form,
                           target_boxes=target_boxes, target_form=target_form)
    for candidates in (original + crop, crop + original):
        decision = _assess_candidates(candidates)
        assert decision.status == "success"
        assert decision.best.materials == {"polyester": 75, "rayon": 21, "spandex": 4}


def test_same_han_suffix_in_two_fibers_uses_two_distinct_physical_rows():
    names = ("聚酯纤维", "聚酰胺纤维", "氨纶")
    original, crop = _pair(source_boxes="two", target_boxes="two", names=names)
    decision = _assess_candidates(original + crop)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 75, "nylon": 21, "spandex": 4}


def _add_lining(candidate):
    heading_words = (_word("OUTER", 120, 45, 120, 20), _word("LINING", 120, 340, 120, 20))
    lining_words = tuple(_word(character, 120 + index * 40, 380, 40)
                         for index, character in enumerate("聚酯纤维"))
    lining_words += (_word("100", 500, 380, 60), _word("%", 565, 380, 20))
    candidate = replace(candidate, image_region=(80, 35, 650, 440))
    return _rebuild(candidate, text="OUTER\n" + candidate.text + "\nLINING\n聚酯纤维 100%",
                    words=candidate.image_words + heading_words + lining_words)


def test_identical_han_fiber_in_outer_and_lining_keeps_both_physical_parts():
    original, crop = _pair(source_boxes="chars", target_boxes="chars")
    original = [_add_lining(original[0])]
    crop = [_add_lining(crop[0])]
    decision = _assess_candidates(original + crop)
    assert decision.status == "success"
    assert decision.best.selected_part == "outer"
    assert decision.best.parts == {"outer": {"polyester": 75, "rayon": 21, "spandex": 4},
                                   "lining": {"polyester": 100}}


@pytest.mark.parametrize("damaged_side", ["source", "target"])
@pytest.mark.parametrize("defect", ["missing_lining_character", "one_percent_box_for_two_parts"])
def test_primary_han_recovery_cannot_borrow_or_hide_secondary_part_annotations(damaged_side, defect):
    original, crop = _pair(source_boxes="chars", target_boxes="chars")
    original = [_add_lining(original[0])]
    crop = [_add_lining(crop[0])]
    selected = original if damaged_side == "source" else crop
    candidate = selected[0]
    words = list(candidate.image_words)
    if defect == "missing_lining_character":
        words = [word for word in words if not (word.text == "纤" and word.top == 380)]
    else:
        outer_percent = next(index for index, word in enumerate(words) if word.text == "%" and word.top == 100)
        words[outer_percent] = next(word for word in words if word.text == "%" and word.top == 380)
    selected[0] = _rebuild(candidate, words=tuple(words))
    decision = _assess_candidates(original + crop)
    assert decision.status == "success"
    assert "outer" in decision.rejected_composition_parts or "generic" in decision.rejected_composition_parts
    # The invalid primary reconstruction remains rejected. Only the literal
    # confirmed lining may survive under the new part selection policy.
    from apps.text.parse_label import parse_label
    response = parse_label(decision.best.text, rejected_composition_parts=decision.rejected_composition_parts,
                           unpaired_ratio_parts=decision.unpaired_ratio_parts,
                           conflicting_parts=decision.conflicting_parts)
    assert response["selected_part"] == "lining"
    assert "outer" not in response["parts"]


@pytest.mark.parametrize("damaged_side", ["source", "target"])
@pytest.mark.parametrize("defect", ["missing_character", "extra_character", "unboxed_literal", "missing_percent",
                                   "duplicate_percent", "split_integer", "wrong_numeric_row", "swapped_character_order",
                                   "nonoverlapping_character", "overlapping_alias_annotation"])
def test_han_crop_cannot_release_incomplete_or_reused_literal_geometry(damaged_side, defect):
    original, crop = _pair(source_boxes="chars", target_boxes="chars")
    selected = original if damaged_side == "source" else crop
    candidate = selected[0]
    words = list(candidate.image_words)
    if defect == "missing_character":
        words.pop(1)
    elif defect == "extra_character":
        words.append(_word("X", 300, 100, 20))
    elif defect == "unboxed_literal":
        candidate = replace(candidate, text=candidate.text.replace("聚酯纤维", "聚酯纤维X", 1))
    elif defect == "missing_percent":
        words = [word for word in words if not (word.text == "%" and word.top == 180)]
    elif defect == "duplicate_percent":
        words.append(_word("%", 590, 180, 20))
    elif defect == "split_integer":
        index = next(index for index, word in enumerate(words) if word.text == "21")
        words[index:index + 1] = [_word("2", 500, 180, 30), _word("1", 530, 180, 30)]
    elif defect == "wrong_numeric_row":
        index = next(index for index, word in enumerate(words) if word.text == "21")
        words[index] = _word("21", 500, 260, 60)
    elif defect == "swapped_character_order":
        first, second = words[0], words[1]
        words[0] = replace(second, text=first.text)
        words[1] = replace(first, text=second.text)
    elif defect == "nonoverlapping_character":
        words[1] = _word(words[1].text, 370, 100, 40)
    else:
        words.append(_word("聚酯", 120, 100, 80))
    selected[0] = _rebuild(candidate, words=tuple(words))
    assert _assess_candidates(original + crop).status == "failed"


@pytest.mark.parametrize("damaged_side", ["source", "target"])
def test_repeated_han_suffix_cannot_reuse_the_other_material_rows_box(damaged_side):
    names = ("聚酯纤维", "聚酰胺纤维", "氨纶")
    original, crop = _pair(source_boxes="two", target_boxes="two", names=names)
    selected = original if damaged_side == "source" else crop
    candidate = selected[0]
    selected[0] = _rebuild(candidate, words=tuple(
        word for word in candidate.image_words if not (word.text == "纤维" and word.top == 180)
    ))
    assert _assess_candidates(original + crop).status == "failed"


@pytest.mark.parametrize("unknown", ["未知纤维", "未知繊維", "人造皮革", "인조"])
@pytest.mark.parametrize("damaged_side", ["source", "target"])
def test_scoped_han_matching_does_not_delete_unknown_or_negating_material_context(unknown, damaged_side):
    original, crop = _pair(source_boxes="two", target_boxes="chars")
    selected = original if damaged_side == "source" else crop
    candidate = selected[0]
    # Every warning character has a box; failure must be semantic, rather than
    # an incidental annotation omission. Han warnings also arrive as boxes.
    fragments = tuple(unknown) if not unknown.isascii() and unknown != "인조" else (unknown,)
    warning_words = tuple(_word(fragment, 120 + index * 35, 300, len(fragment) * 35, 15)
                          for index, fragment in enumerate(fragments))
    selected[0] = _rebuild(candidate, text=candidate.text + "\n" + unknown,
                          words=candidate.image_words + warning_words)
    assert _assess_candidates(original + crop).status == "failed"


@pytest.mark.parametrize("number", [".5", "0.5", "5.0"])
def test_registered_han_boxes_do_not_turn_decimal_components_into_a_missing_digit(number):
    original, crop = _pair(number=number, source_boxes="two", target_boxes="chars")
    assert _assess_candidates(original + crop).status == "failed"


def test_one_crop_raw_and_layout_are_not_two_independent_han_numeric_corrections():
    original = _reading("74", boxes="two")
    layout = "聚酯 纤维 75%\n人造 丝 21%\n氨纶 4%"
    crop = _reading("75", boxes="chars", source="material_crop",
                    variant="one-crop-input", layout=layout)
    assert len(crop) == 2 and all(candidate.parser_status == "success" for candidate in crop)
    assert _assess_candidates(original + crop).status == "failed"


def test_two_actual_han_rereads_retain_existing_independent_digit_substitution_proof():
    original, crop = _pair(number="74", source_boxes="two", target_boxes="chars")
    rotated = _reading("75", boxes="two", source="material_crop_rotated",
                       variant="second-physical-input")
    assert _assess_candidates(original + crop).status == "failed"
    decision = _assess_candidates(original + crop + rotated)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 75, "rayon": 21, "spandex": 4}
