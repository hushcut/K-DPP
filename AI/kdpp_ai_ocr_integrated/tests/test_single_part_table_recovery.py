"""Require a literal part, complete name, percentage and exclusion boundary."""

from dataclasses import replace

import pytest

from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.parse_label import parse_label
from apps.text.single_part_table_recovery import literal_single_part_table_over_failed_layout, verified_single_part_layout
from apps.text.headed_inline_recovery import literal_tokens


CAPTION = "(심지, 상표, 보강재, 자수, 장식 제외)"


def box(text, x, y, width, height=50):
    return OcrWord(text, x, y, x + width, y + height,
                   ((x, y), (x + width, y), (x + width, y + height), (x, y + height)))


def readings(fiber="POLYESTER", split_footer=False):
    footer = (box(CAPTION, 100, 320, 750),)
    if split_footer:
        footer = tuple(box(text, x, 320, width) for text, x, width in [
            ("(심지,", 100, 100), ("상표,", 230, 100), ("보강재,", 360, 120),
            ("자수,", 510, 90), ("장식", 620, 90), ("제외)", 730, 100),
        ])
    words = (box("SIZE M", 100, 50, 200), box("혼용률", 100, 140, 140),
             box("겉감", 100, 220, 100), box(":", 210, 220, 20), box(fiber, 250, 220, 250),
             box("100", 650, 210, 100), box("%", 760, 210, 40)) + footer
    raw = build_candidate("original", f"SIZE M\n혼용률\n겉감: {fiber}\n100%\n{CAPTION}",
                          parse_candidate=parse_label)
    layout = build_candidate("original", f"SIZE M\n혼용률 100%\n겉감: {fiber}\n{CAPTION}",
                             parse_candidate=parse_label, layout_used=True)
    return tuple(replace(item, image_key="photo", image_variant_key="original-reply",
                         image_region=(0., 0., 1400., 1000.), image_words=words) for item in (raw, layout))


@pytest.mark.parametrize("fiber", ["POLYESTER", "COTTON", "NYLON"])
@pytest.mark.parametrize("split_footer", [False, True])
def test_one_registered_outer_fiber_and_literal_100_percent_are_verified(fiber, split_footer):
    raw, layout = readings(fiber, split_footer)
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    assert literal_single_part_table_over_failed_layout(raw, layout)
    assert raw.selected_part == "outer"


def test_a_bent_registered_name_is_preserved_without_repairing_its_characters():
    raw, layout = readings("폴리에스터")
    first = OcrWord("폴리", 250, 220, 390, 282,
                    ((250, 220), (390, 232), (390, 282), (250, 270)))
    second = box("에스터", 405, 225, 100)
    words = raw.image_words[:4] + (first, second) + raw.image_words[5:]
    raw, layout = (replace(item, image_words=words) for item in (raw, layout))
    assert literal_single_part_table_over_failed_layout(raw, layout)


@pytest.mark.parametrize("size", [90, 95])
def test_an_extra_literal_size_number_remains_separate_from_the_percent(size):
    raw, layout = readings()
    words = (replace(raw.image_words[0], text=f"SIZE {size}"),) + raw.image_words[1:]
    raw, layout = (replace(item, text=item.text.replace("SIZE M", f"SIZE {size}"), image_words=words)
                   for item in (raw, layout))
    layout = replace(layout, observed_ratios={"generic": [100], "outer": [size]})
    assert literal_single_part_table_over_failed_layout(raw, layout)


def test_metadata_cannot_supply_a_new_number_or_a_duplicate_occurrence():
    raw, layout = readings()
    words = (replace(raw.image_words[0], text="SIZE 90"),) + raw.image_words[1:]
    raw, layout = (replace(item, text=item.text.replace("SIZE M", "SIZE 90"), image_words=words)
                   for item in (raw, layout))
    for ratios in ([100, 91], [100, 90, 90], [90]):
        assert not literal_single_part_table_over_failed_layout(
            raw, replace(layout, observed_ratios={"generic": ratios}),
        )


@pytest.mark.parametrize("defect", [
    "different_photo", "different_reply", "different_source", "missing_geometry",
    "changed_digit", "successful_conflict", "missing_caption", "changed_caption",
    "extra_fiber", "extra_ratio", "other_part", "uncertain_raw", "bad_percentage_position",
])
def test_missing_changed_or_conflicting_evidence_is_never_released(defect):
    raw, layout = readings()
    if defect == "different_photo":
        layout = replace(layout, image_key="other")
    elif defect == "different_reply":
        layout = replace(layout, image_variant_key="crop")
    elif defect == "different_source":
        raw, layout = (replace(item, source="preprocessed") for item in (raw, layout))
    elif defect == "missing_geometry":
        words = list(raw.image_words)
        words[4] = replace(words[4], vertices=())
        raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("100", "99"))
    elif defect == "successful_conflict":
        layout = replace(layout, parser_status="success", parts={"outer": {"cotton": 100}})
    elif defect in {"missing_caption", "changed_caption"}:
        replacement = "" if defect == "missing_caption" else CAPTION.replace("제외", "포함")
        words = raw.image_words[:-1] + ((replace(raw.image_words[-1], text=replacement),) if replacement else ())
        raw, layout = (replace(item, text=item.text.replace(CAPTION, replacement), image_words=words)
                       for item in (raw, layout))
    elif defect == "extra_fiber":
        layout = replace(layout, observed_materials={"outer": ["polyester", "cotton"]})
    elif defect == "extra_ratio":
        layout = replace(layout, observed_ratios={"generic": [100, 5]})
    elif defect == "other_part":
        layout = replace(layout, observed_materials={"lining": ["polyester"]})
    elif defect == "uncertain_raw":
        raw = replace(raw, rejected_composition_parts={"outer": ("unpaired_material_rows",)})
    else:
        words = list(raw.image_words)
        for i in (5, 6):
            w = words[i]
            words[i] = replace(w, top=w.top + 300, bottom=w.bottom + 300,
                               vertices=tuple((x, y + 300) for x, y in w.vertices))
        raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not literal_single_part_table_over_failed_layout(raw, layout)


@pytest.mark.parametrize("extra", ["UNKNOWN", "XYZ", "?", "5"])
def test_other_words_or_numbers_between_the_fiber_and_percentage_remain_evidence(extra):
    raw, layout = readings()
    raw, layout = (replace(item, text=item.text + "\n" + extra,
                           image_words=item.image_words + (box(extra, 550, 220, 60),))
                   for item in (raw, layout))
    assert not literal_single_part_table_over_failed_layout(raw, layout)


def test_production_payload_keeps_raw_and_the_verified_geometric_view():
    from apps.text.ocr_text import OcrPayload, _build_payload_candidates

    raw, layout = readings()
    candidates = _build_payload_candidates(
        "original", OcrPayload(text=raw.text, layout_text=layout.text, layout_words=raw.image_words),
        image_key=raw.image_key, image_variant_key=raw.image_variant_key,
        image_region=raw.image_region, image_transform=(1., 0., 0., 0., 1., 0.),
    )
    assert len(candidates) == 2
    assert candidates[0].text == raw.text
    assert candidates[1].layout_used
    assert candidates[1].parser_confidence == "high"
    assert candidates[1].parts == raw.parts
    assert candidates[1].image_words == raw.image_words
    assert candidates[1].image_variant_key == raw.image_variant_key


def test_rendering_moves_only_the_original_percentage_and_preserves_all_tokens():
    from collections import Counter

    raw, layout = readings()
    rendered = verified_single_part_layout(raw, layout)
    assert rendered is not None
    assert "겉감: POLYESTER 100%" in rendered
    assert Counter(literal_tokens(rendered)) == Counter(literal_tokens(raw.text))
    assert parse_label(rendered)["parts"] == raw.parts
    assert "겉감: POLYESTER\n100%" in raw.text


def test_no_rendering_is_created_without_matching_proof():
    raw, layout = readings()
    assert verified_single_part_layout(raw, replace(layout, image_key="another-photo")) is None
