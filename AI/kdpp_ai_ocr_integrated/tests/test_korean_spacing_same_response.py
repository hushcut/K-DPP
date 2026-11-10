"""A literal outer row may survive spaces added by its own layout view."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def word(text, x, y, width, *, angle=0):
    theta = radians(angle)
    points = tuple((round(px * cos(theta) - py * sin(theta) + 400),
                    round(px * sin(theta) + py * cos(theta) + 400))
                   for px, py in ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24)))
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), points)


def readings(*, angle=0, prefix="", suffix="", care_before_heading="", body="겉감 폴리에스테르 100%",
             layout_body="겉감 폴리 에스테르\n100 %", extra_words=()):
    heading, care = "<섬유의 조성 및 혼용율>", "<취급주의 표기>"
    rows = [heading, body, care, "MADE IN KOREA"]
    layout_rows = [heading, layout_body, care, "MADE IN KOREA"]
    words = (
        word(heading, 10, 20, 320, angle=angle),
        word("겉감", 10, 90, 55, angle=angle),
        word("폴리", 100, 90, 45, angle=angle),
        word("에스테르", 150, 90, 100, angle=angle),
        word("100", 350, 90, 50, angle=angle),
        word("%", 410, 90, 20, angle=angle),
        word(care, 10, 170, 240, angle=angle),
        word("MADE IN KOREA", 10, 240, 240, angle=angle),
    ) + tuple(extra_words)
    if care_before_heading:
        rows.insert(2, care_before_heading)
        layout_rows.insert(3, care_before_heading)
        words += (word(care_before_heading, 10, 210, 180, angle=angle),)
    if prefix:
        rows.insert(0, prefix)
        layout_rows.insert(0, prefix)
        words += (word(prefix, 10, -50, 120, angle=angle),)
    if suffix:
        rows.append(suffix)
        layout_rows.append(suffix)
        words += (word(suffix, 10, 300, 120, angle=angle),)
    return _build_payload_candidates(
        "original", OcrPayload("\n".join(rows), "\n".join(layout_rows), layout_words=words),
        image_key="one-photo", image_variant_key="one-response", image_region=(0, 0, 1600, 1600),
        image_transform=(1, 0, 0, 0, 1, 0),
    )


@pytest.mark.parametrize("angle", [-6, 0, 6, 90])
@pytest.mark.parametrize("prefix", ["", "BRAND"])
@pytest.mark.parametrize("care_before_heading", ["", "손세탁"])
def test_same_response_spacing_keeps_one_coordinate_proved_outer_row(angle, prefix, care_before_heading):
    raw, layout = readings(angle=angle, prefix=prefix, care_before_heading=care_before_heading)
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    assert same_region_recovery(layout, raw, "outer", [raw, layout])
    decision = _assess_candidates([raw, layout])
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 100}
    assert decision.best.selected_part == "outer"


@pytest.mark.parametrize("defect", [
    "image", "source", "variant", "region", "word_text", "word_bounds", "raw_is_layout",
    "missing_variant", "missing_region", "extra_reason", "extra_part", "changed_ratio",
    "missing_character", "reordered_name", "other_observed_material", "other_observed_ratio",
])
def test_spacing_recovery_requires_the_same_complete_response(defect):
    raw, layout = readings()
    if defect == "image":
        raw = replace(raw, image_key="another-photo")
    elif defect == "source":
        raw = replace(raw, source="material_crop")
    elif defect == "variant":
        raw = replace(raw, image_variant_key="another-input")
    elif defect == "region":
        raw = replace(raw, image_region=(0, 0, 1700, 1600))
    elif defect == "word_text":
        raw = replace(raw, image_words=(replace(raw.image_words[2], text="나일론"),) + raw.image_words[1:])
    elif defect == "word_bounds":
        raw = replace(raw, image_words=(replace(raw.image_words[0], left=999),) + raw.image_words[1:])
    elif defect == "raw_is_layout":
        raw = replace(raw, layout_used=True)
    elif defect == "missing_variant":
        layout = replace(layout, image_variant_key="")
    elif defect == "missing_region":
        layout = replace(layout, image_region=())
    elif defect == "extra_reason":
        layout = replace(layout, rejected_composition_parts={"outer": ("unresolved_material_token",)})
    elif defect == "extra_part":
        layout = replace(layout, rejected_composition_parts=layout.rejected_composition_parts | {
            "lining": ("unpaired_material_rows",),
        })
    elif defect == "changed_ratio":
        layout = replace(layout, text=layout.text.replace("100", "10"))
    elif defect == "missing_character":
        layout = replace(layout, text=layout.text.replace("에스테르", "에스테"))
    elif defect == "reordered_name":
        layout = replace(layout, text=layout.text.replace("폴리 에스테르", "에스테르 폴리"))
    elif defect == "other_observed_material":
        layout = replace(layout, observed_materials={"outer": ["cotton"]})
    else:
        layout = replace(layout, observed_ratios={"outer": [10]})
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("defect", ["missing_polygon", "opposite", "other_row", "other_page", "degenerate"])
def test_each_marker_name_and_ratio_box_needs_valid_local_geometry(index, defect):
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[index]
    if defect == "missing_polygon":
        words[index] = replace(old, vertices=())
    elif defect == "opposite":
        a, b, c, d = old.vertices
        words[index] = replace(old, vertices=(b, a, d, c))
    elif defect == "other_row":
        points = tuple((x, y + 100) for x, y in old.vertices)
        words[index] = replace(old, top=old.top + 100, bottom=old.bottom + 100, vertices=points)
    elif defect == "other_page":
        words[index] = replace(old, page=1)
    else:
        words[index] = replace(old, vertices=((old.left, old.top),) * 4)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])


@pytest.mark.parametrize("extra", ["UNKNOWN", "OLEFIN", "FAUX", "NYLON 10%", "10%", "안감 면 100%"])
def test_spacing_does_not_discard_extra_material_ratio_or_part(extra):
    raw, layout = readings(suffix=extra)
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])
    assert _assess_candidates([raw, layout]).status == "failed"


@pytest.mark.parametrize("defect", ["missing_heading", "missing_care_heading", "unknown_between",
                                   "opaque_beside_row", "overlapping_annotation"])
def test_fences_and_the_entire_physical_row_are_preserved(defect):
    raw, layout = readings()
    if defect == "missing_heading":
        raw, layout = (replace(item, text=item.text.replace("<섬유의 조성 및 혼용율>", "UNKNOWN TITLE"),
                               image_words=tuple(replace(w, text="UNKNOWN TITLE") if w.text == "<섬유의 조성 및 혼용율>" else w
                                                 for w in item.image_words))
                       for item in (raw, layout))
    elif defect == "missing_care_heading":
        raw, layout = (replace(item, text=item.text.replace("<취급주의 표기>", "UNKNOWN TITLE"),
                               image_words=tuple(replace(w, text="UNKNOWN TITLE") if w.text == "<취급주의 표기>" else w
                                                 for w in item.image_words))
                       for item in (raw, layout))
    elif defect == "unknown_between":
        extra = word("MYSTERY", 10, 130, 150)
        raw, layout = (replace(item, text=item.text.replace("<취급주의 표기>", "MYSTERY\n<취급주의 표기>"),
                               image_words=item.image_words + (extra,)) for item in (raw, layout))
    elif defect == "opaque_beside_row":
        raw, layout = readings(prefix="BRAND")
        words = list(raw.image_words)
        old = words[-1]
        points = tuple((x, y + 140) for x, y in old.vertices)
        words[-1] = replace(old, top=old.top + 140, bottom=old.bottom + 140, vertices=points)
        raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    else:
        words = raw.image_words + (replace(raw.image_words[2], text="여분"),)
        raw, layout = (replace(item, image_words=words) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])


@pytest.mark.parametrize("caption", ["손세탁 ?", "손세탁 UNKNOWN", "HAND WASH 30", "30", "UNKNOWN"])
def test_only_one_complete_literal_care_caption_can_precede_the_heading(caption):
    raw, layout = readings(care_before_heading=caption)
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])


@pytest.mark.parametrize("shift", [-120, -260])
def test_optional_care_caption_must_really_be_below_the_material_row(shift):
    raw, layout = readings(care_before_heading="손세탁")
    words = list(raw.image_words)
    old = words[-1]
    points = tuple((x, y + shift) for x, y in old.vertices)
    words[-1] = replace(old, top=old.top + shift, bottom=old.bottom + shift, vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])


def test_care_caption_does_not_skip_another_care_row_before_the_heading():
    raw, layout = readings(care_before_heading="손세탁")
    extra = word("별도 세탁", 210, 210, 160)
    raw, layout = (replace(item, text=item.text.replace("손세탁", "손세탁\n별도 세탁"),
                           image_words=item.image_words + (extra,)) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])


@pytest.mark.parametrize("location", ["layout", "words"])
def test_registered_ocr_correction_is_not_evidence_of_unchanged_characters(location):
    raw, layout = readings()
    if location == "layout":
        layout = replace(layout, text=layout.text.replace("폴리", "포리"))
    else:
        words = tuple(replace(w, text="포리") if w.text == "폴리" else w for w in raw.image_words)
        raw, layout = (replace(item, image_words=words) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "outer", [raw, layout])
