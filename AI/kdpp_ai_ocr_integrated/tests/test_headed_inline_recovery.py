"""Literal physical pairs may survive a shuffled view of one original reply."""

from dataclasses import replace
import math

import pytest

from apps.text.headed_inline_recovery import literal_headed_blend_over_failed_layout, _pixel_rounded_pair
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.parse_label import parse_label


def box(text, x, y, width, height=50):
    return OcrWord(text, x, y, x + width, y + height,
                   ((x, y), (x + width, y), (x + width, y + height), (x, y + height)))


def readings():
    words = (box("소재", 100, 200, 110), box(":", 215, 200, 25),
             box("면", 280, 200, 70), box("80", 360, 200, 90), box("%", 460, 200, 60),
             box(",", 530, 200, 20), box("폴리", 580, 200, 160), box("에스터", 750, 200, 220),
             box("20", 980, 200, 90), box("%", 1080, 200, 60), box("손세탁", 100, 450, 200))
    raw = build_candidate("original", "소재: 면80%, 폴리에스터20%\n손세탁", parse_candidate=parse_label)
    layout = build_candidate("original", "80% 폴리에스터20%\n소재: 면,\n손세탁",
                             parse_candidate=parse_label, layout_used=True)
    return tuple(replace(item, image_key="same-photo", image_variant_key="same-response",
                         image_region=(0., 0., 1600., 900.), image_words=words) for item in (raw, layout))


def test_exact_pairs_and_header_can_preserve_the_literal_original():
    raw, layout = readings()
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    assert literal_headed_blend_over_failed_layout(raw, layout)


def test_locally_bent_cells_preserve_their_own_literal_pairs():
    raw, layout = readings()
    curved = []
    for index, word in enumerate(raw.image_words):
        angle = -5 if index < 2 else -2 if index < 6 else 2 if index < 10 else 0
        ox = 100 if index < 2 else 280 if index < 6 else 580
        theta = math.radians(angle)
        points = tuple((round(ox + (x - ox) * math.cos(theta) - (y - 200) * math.sin(theta)),
                        round(200 + (x - ox) * math.sin(theta) + (y - 200) * math.cos(theta)))
                       for x, y in word.vertices)
        xs, ys = zip(*points)
        curved.append(replace(word, left=min(xs), right=max(xs), top=min(ys), bottom=max(ys), vertices=points))
    raw, layout = (replace(item, image_words=tuple(curved)) for item in (raw, layout))
    assert literal_headed_blend_over_failed_layout(raw, layout)


@pytest.mark.parametrize("with_frame", [False, True])
def test_production_payload_discards_only_the_proved_same_response_view(with_frame):
    from apps.text.ocr_text import OcrPayload, _build_payload_candidates

    raw, layout = readings()
    payload = OcrPayload(text=raw.text, layout_text=layout.text, layout_words=raw.image_words)
    candidates = _build_payload_candidates(
        "original", payload, image_key=raw.image_key,
        image_variant_key=raw.image_variant_key, image_region=raw.image_region,
        image_transform=(1., 0., 0., 0., 1., 0.) if with_frame else None,
    )
    assert len(candidates) == (1 if with_frame else 2)
    assert candidates[0].text == raw.text


@pytest.mark.parametrize("defect", [
    "other_image", "other_variant", "other_source", "successful_layout", "changed_digit",
    "changed_word", "missing_box", "missing_polygon", "reversed_box", "bad_bounds",
    "extra_ratio", "extra_material", "other_part", "other_reason", "no_heading",
])
def test_other_readings_and_unproved_or_conflicting_evidence_are_never_discarded(defect):
    raw, layout = readings()
    if defect == "other_image":
        layout = replace(layout, image_key="another-photo")
    elif defect == "other_variant":
        layout = replace(layout, image_variant_key="crop")
    elif defect == "other_source":
        raw, layout = (replace(item, source="preprocessed") for item in (raw, layout))
    elif defect == "successful_layout":
        layout = replace(layout, parser_status="success", parts=raw.parts)
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("80", "70"))
    elif defect == "changed_word":
        layout = replace(layout, text=layout.text.replace("면", "모"))
    elif defect in {"missing_box", "missing_polygon", "reversed_box", "bad_bounds"}:
        words = list(raw.image_words)
        if defect == "missing_box":
            words.pop(3)
        elif defect == "missing_polygon":
            words[3] = replace(words[3], vertices=())
        elif defect == "reversed_box":
            a, b, c, d = words[3].vertices
            words[3] = replace(words[3], vertices=(b, a, d, c))
        else:
            words[3] = replace(words[3], left=-40)
        raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    elif defect == "extra_ratio":
        layout = replace(layout, observed_ratios={"generic": [80, 20, 5]})
    elif defect == "extra_material":
        layout = replace(layout, observed_materials={"generic": ["cotton", "polyester", "nylon"]})
    elif defect == "other_part":
        layout = replace(layout, observed_ratios={"generic": [80, 20], "lining": [100]})
    elif defect == "other_reason":
        layout = replace(layout, rejected_composition_parts={"generic": ("unresolved_material_token",)})
    else:
        raw = replace(raw, text=raw.text.replace("소재:", "OTHER:"))
    assert not literal_headed_blend_over_failed_layout(raw, layout)


@pytest.mark.parametrize("extra", ["UNKNOWN", "NYLON", "5%", "?", "LINING"])
def test_opaque_words_between_pairs_cannot_be_fenced_off(extra):
    raw, layout = readings()
    # Keep the literal token inventories equal in both views and annotations.
    # Geometry must still reject the extra word inside the composition band.
    words = raw.image_words + (box(extra, 552, 205, 20),)
    raw, layout = (replace(item, text=item.text + "\n" + extra, image_words=words)
                   for item in (raw, layout))
    assert not literal_headed_blend_over_failed_layout(raw, layout)


@pytest.mark.parametrize("pixels,expected", [(0, True), (1, True), (2, False), (4, False)])
def test_word_edge_rounding_is_bounded_to_one_pixel_on_both_edges(pixels, expected):
    # One long word sets a flat frame. The other is just past 3 degrees;
    # only the displacement caused by at most one integer pixel is allowed.
    rise = math.tan(math.radians(3)) * 200 + pixels
    word = OcrWord("NYLON", 0, 100, 200, 160,
                   ((0, 100 - rise / 2), (200, 100 + rise / 2),
                    (200, 150 + rise / 2), (0, 150 - rise / 2)))
    anchor = box("80%", 220, 100, 300)
    assert _pixel_rounded_pair("NYLON 80%", (word, anchor)) is expected
