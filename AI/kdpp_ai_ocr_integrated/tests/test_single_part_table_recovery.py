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


def test_a_missing_comma_between_written_exclusion_items_changes_no_fiber():
    raw, layout = readings(split_footer=True)
    for old in (raw, layout):
        changed = replace(old, text=old.text.replace("자수, 장식", "자수 장식"),
                          image_words=tuple(replace(w, text="자수") if w.text == "자수," else w
                                            for w in old.image_words))
        if old is raw:
            raw = changed
        else:
            layout = changed
    assert literal_single_part_table_over_failed_layout(raw, layout)


@pytest.mark.parametrize("source", ["preprocessed", "material_crop", "material_crop_rotated"])
def test_a_scrambled_reread_uses_its_own_raw_table_and_same_place_original(source):
    from apps.text.single_part_table_recovery import recover_corroborated_single_part_layout

    original, layout = readings()
    raw = replace(original, source=source, image_variant_key="reread")
    layout = replace(layout, source=source, image_variant_key="reread")
    assert not literal_single_part_table_over_failed_layout(raw, layout)
    for part in ("generic", "outer", "embroidery_yarn"):
        assert recover_corroborated_single_part_layout(layout, original, part, [original, raw, layout])
    assert not recover_corroborated_single_part_layout(layout, original, "lining", [original, raw, layout])


def test_corroborating_original_cannot_hide_an_unconfirmed_outer_part():
    from apps.text.single_part_table_recovery import recover_corroborated_single_part_layout

    original, layout = readings()
    raw = replace(original, source="material_crop", image_variant_key="crop")
    layout = replace(layout, source="material_crop", image_variant_key="crop")
    original = replace(original, unconfirmed_outer_parts=("outer_2",))
    assert not recover_corroborated_single_part_layout(layout, original, "outer", [original,raw,layout])


@pytest.mark.parametrize("defect", ["missing_raw", "other_image", "same_variant", "other_fiber",
                                  "unknown_fiber", "moved_footer", "extra_ratio", "unknown_between",
                                  "missing_geometry", "wrong_part", "actual_embroidery", "missing_percent"])
def test_reread_recovery_cannot_hide_real_evidence_or_borrow_other_source(defect):
    from apps.text.single_part_table_recovery import recover_corroborated_single_part_layout

    original, layout = readings()
    raw = replace(original, source="material_crop", image_variant_key="crop")
    layout = replace(layout, source="material_crop", image_variant_key="crop")
    candidates = [original, raw, layout]
    if defect == "missing_raw":
        candidates = [original, layout]
    elif defect == "other_image":
        original = replace(original, image_key="other-photo")
    elif defect == "same_variant":
        original = replace(original, image_variant_key="crop")
    elif defect == "other_fiber":
        original = replace(original, parts={"outer": {"cotton": 100}})
    elif defect in {"unknown_fiber", "actual_embroidery"}:
        raw = replace(raw, parts={"outer": {"polyester": 90}, "embroidery_yarn": {"nylon": 10}})
        candidates = [original, raw, layout]
    elif defect in {"moved_footer", "missing_geometry", "unknown_between"}:
        words = raw.image_words
        if defect == "moved_footer":
            words = words[:-1] + (box(CAPTION,100,700,750),)
        elif defect == "missing_geometry":
            words = (replace(words[0], vertices=()),) + words[1:]
        else:
            words = words + (box("UNKNOWN", 550, 220, 60),)
        raw, layout = (replace(item, image_words=words,
                               text=item.text + ("\nUNKNOWN" if defect == "unknown_between" else ""))
                       for item in (raw, layout))
        candidates = [original, raw, layout]
    elif defect == "extra_ratio":
        layout = replace(layout, observed_ratios={"generic": [100, 5]})
    elif defect == "wrong_part":
        raw = replace(raw, parts={"lining": {"polyester": 100}})
        candidates = [original, raw, layout]
    elif defect == "missing_percent":
        words = raw.image_words[:5] + raw.image_words[7:]
        raw, layout = (replace(item, image_words=words, text=item.text.replace("100%", ""))
                       for item in (raw, layout))
        candidates = [original, raw, layout]
    assert not recover_corroborated_single_part_layout(layout, original, "outer", candidates)


def test_a_percentage_swallowed_by_reordered_exclusion_text_still_needs_its_real_cell():
    raw, old = readings(split_footer=True)
    text = f"SIZE M\n혼용률\n겉감: POLYESTER\n{CAPTION.replace('자수', '100% 자수')}"
    layout = replace(build_candidate("original", text, parse_candidate=parse_label, layout_used=True),
                     image_key=old.image_key, image_variant_key=old.image_variant_key,
                     image_region=old.image_region, image_words=old.image_words)
    assert not any(100 in values for values in layout.observed_ratios.values())
    assert literal_single_part_table_over_failed_layout(raw, layout)
    rendered = verified_single_part_layout(raw, layout)
    assert rendered and parse_label(rendered)["materials"] == {"polyester": 100}


@pytest.mark.parametrize("noun", ["실체", "부속물"])
def test_literal_nonfiber_exclusion_noun_is_retained_without_spelling_repair(noun):
    raw, layout = readings()
    caption = CAPTION.replace("심지", noun)
    def changed(item):
        parsed = build_candidate(item.source, item.text.replace(CAPTION, caption),
                                 parse_candidate=parse_label, layout_used=item.layout_used)
        return replace(parsed, image_key=item.image_key, image_variant_key=item.image_variant_key,
                       image_region=item.image_region, image_words=item.image_words[:-1] +
                       (replace(item.image_words[-1], text=caption),))
    raw, layout = changed(raw), changed(layout)
    rendered = verified_single_part_layout(raw, layout)
    assert rendered and caption in rendered
    assert "심지" not in rendered


@pytest.mark.parametrize("noun", ["면", "나일론", "COTTON", "UNKNOWN", "부속물 5%"])
def test_fiber_or_numeric_text_cannot_supply_the_exclusion_noun(noun):
    raw, layout = readings()
    caption = CAPTION.replace("심지", noun)
    raw, layout = (replace(item, text=item.text.replace(CAPTION, caption),
                           image_words=item.image_words[:-1] + (replace(item.image_words[-1], text=caption),))
                   for item in (raw, layout))
    assert not literal_single_part_table_over_failed_layout(raw, layout)


def curved_cells():
    from math import cos, radians, sin
    def tilted(text, x, y, width, angle):
        c, s = cos(radians(angle)), sin(radians(angle))
        vertices = tuple((round(x + px * c - py * s), round(y + px * s + py * c))
                         for px, py in ((0, 0), (width, 0), (width, 30), (0, 30)))
        xs, ys = zip(*vertices)
        return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)
    alias = (tilted("폴리", 100, 100, 100, 10), tilted("에스터", 210, 120, 160, 10))
    percent = (tilted("100", 440, 156, 100, 2), tilted("%", 550, 160, 40, 2))
    return alias, percent, tilted


def test_split_literal_alias_and_percentage_can_follow_a_bounded_curved_baseline():
    from apps.text.single_part_table_recovery import _curved_name_ratio
    alias, percentage, _ = curved_cells()
    assert _curved_name_ratio("폴리에스터", alias, percentage, alias + percentage)
    assert not _curved_name_ratio("에스터", alias[-1:], percentage, alias[-1:] + percentage)


@pytest.mark.parametrize("defect", ["steep", "different_row", "far", "left", "intrusion", "wrong_name"])
def test_a_curve_does_not_join_different_rows_or_hide_intervening_evidence(defect):
    from apps.text.single_part_table_recovery import _curved_name_ratio
    alias, percentage, tilted = curved_cells()
    name = "폴리에스터"
    if defect == "steep":
        percentage = (tilted("100%", 440, 156, 140, 25),)
    elif defect == "different_row":
        percentage = (tilted("100%", 440, 300, 140, 2),)
    elif defect == "far":
        percentage = (tilted("100%", 1500, 270, 140, 2),)
    elif defect == "left":
        percentage = (tilted("100%", 0, 100, 60, 2),)
    elif defect == "wrong_name":
        name = "폴리에스더"
    words = alias + percentage
    if defect == "intrusion":
        words += (box("UNKNOWN", 395, 155, 35, 25),)
    assert not _curved_name_ratio(name, alias, percentage, words)
