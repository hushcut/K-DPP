"""Account for literal metadata while preserving a complete unheaded blend."""

from dataclasses import replace

import pytest

from apps.text.headed_inline_recovery import (
    literal_headed_blend_over_failed_layout, literal_unheaded_blend_over_failed_layout,
)
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.parse_label import parse_label


def box(text, x, y, width):
    return OcrWord(text, x, y, x + width, y + 50,
                   ((x, y), (x + width, y), (x + width, y + 50), (x, y + 50)))


def readings(vertical=False):
    words = (box("WASHING INSTRUCTIONS", 100, 100, 400), box("30", 100, 200, 90),
             box("HAND WASH", 100, 300, 240), box("POLYESTER", 100, 500, 220),
             box("70", 330, 500, 90), box("%", 430, 500, 60), box(",", 500, 500, 20),
             box("RAYON", 700, 500, 180), box("30", 890, 500, 90), box("%", 990, 500, 60))
    if vertical:
        transformed = []
        for word in words:
            points = tuple((900 - y, x) for x, y in word.vertices)
            xs, ys = zip(*points)
            transformed.append(replace(word, left=min(xs), right=max(xs), top=min(ys), bottom=max(ys), vertices=points))
        words = tuple(transformed)
    raw = build_candidate("original", "WASHING INSTRUCTIONS\n30\nHAND WASH\nPOLYESTER70%, RAYON30%",
                          parse_candidate=parse_label)
    layout = build_candidate("original", "WASHING INSTRUCTIONS\n30\n70% POLYESTER30%\nRAYON,\nHAND WASH",
                             parse_candidate=parse_label, layout_used=True)
    return tuple(replace(item, image_key="one-photo", image_variant_key="one-response",
                         image_region=(0., 0., 1500., 1500.), image_words=words) for item in (raw, layout))


@pytest.mark.parametrize("vertical", [False, True])
def test_literal_metadata_number_and_pairs_survive_reordered_rows(vertical):
    raw, layout = readings(vertical)
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    assert not literal_headed_blend_over_failed_layout(raw, layout)
    assert literal_unheaded_blend_over_failed_layout(raw, layout)
    assert raw.selected_part == "generic"


@pytest.mark.parametrize("ratios", [[70, 30, 5], [70, 30, 30, 30], [70, 30, 1]])
def test_new_numbers_or_excess_metadata_occurrences_remain_blocked(ratios):
    raw, layout = readings()
    layout = replace(layout, observed_ratios={"generic": ratios})
    assert not literal_unheaded_blend_over_failed_layout(raw, layout)


@pytest.mark.parametrize("defect", [
    "other_part", "other_photo", "other_reply", "changed_token", "missing_word",
    "extra_fiber", "successful_conflict", "unread_raw", "unproved_heading",
])
def test_other_parts_and_unproved_or_different_readings_are_not_discarded(defect):
    raw, layout = readings()
    if defect == "other_part":
        layout = replace(layout, observed_ratios={"generic": [70, 30], "outer": [30]})
    elif defect == "other_photo":
        layout = replace(layout, image_key="different")
    elif defect == "other_reply":
        layout = replace(layout, image_variant_key="different")
    elif defect == "changed_token":
        layout = replace(layout, text=layout.text.replace("70", "75"))
    elif defect == "missing_word":
        raw, layout = (replace(item, image_words=item.image_words[:-1]) for item in (raw, layout))
    elif defect == "extra_fiber":
        layout = replace(layout, observed_materials={"generic": ["polyester", "rayon", "cotton"]})
    elif defect == "successful_conflict":
        layout = replace(layout, parser_status="success", parts={"generic": {"polyester": 30, "rayon": 70}})
    elif defect == "unread_raw":
        raw = replace(raw, rejected_composition_parts={"generic": ("unpaired_material_rows",)})
    else:
        raw, layout = (replace(item, text=item.text.replace("POLYESTER", "UNKNOWN POLYESTER"),
                               image_words=item.image_words + (box("UNKNOWN", 20, 500, 70),))
                       for item in (raw, layout))
    assert not literal_unheaded_blend_over_failed_layout(raw, layout)


@pytest.mark.parametrize("extra", ["UNKNOWN", "?", "5%"])
def test_opaque_or_numeric_words_between_the_pairs_stay_evidence(extra):
    raw, layout = readings()
    raw, layout = (replace(item, text=item.text + "\n" + extra,
                           image_words=item.image_words + (box(extra, 570, 500, 70),))
                   for item in (raw, layout))
    assert not literal_unheaded_blend_over_failed_layout(raw, layout)


def test_production_payload_preserves_the_verified_unheaded_original():
    from apps.text.ocr_text import OcrPayload, _build_payload_candidates

    raw, layout = readings()
    candidates = _build_payload_candidates(
        "original", OcrPayload(text=raw.text, layout_text=layout.text, layout_words=raw.image_words),
        image_key=raw.image_key, image_variant_key=raw.image_variant_key,
        image_region=raw.image_region, image_transform=(1., 0., 0., 0., 1., 0.),
    )
    assert len(candidates) == 1
    assert candidates[0].text == raw.text
    assert candidates[0].selected_part == "generic"


def test_oppositely_facing_cells_cannot_be_merged_into_one_unheaded_blend():
    raw, layout = readings()
    words = list(raw.image_words)
    for index in (7, 8, 9):
        word = words[index]
        points = tuple((1750 - x, 1050 - y) for x, y in word.vertices)
        xs, ys = zip(*points)
        words[index] = replace(word, left=min(xs), right=max(xs), top=min(ys), bottom=max(ys), vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not literal_unheaded_blend_over_failed_layout(raw, layout)
