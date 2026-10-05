"""A percent glyph misread needs two complete, independent physical rereads."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _percent_glyph_recovery, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


REGION = (0, 0, 500, 400)
CROP_REGION = (0, 0, 500, 160)


def _word(text, x, y, width, *, tilted=False):
    points = ((x, y), (x + width, y), (x + width, y + 20), (x, y + 20))
    if tilted:
        points = tuple((px, py + round(px / 5)) for px, py in points)
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), points)


def _candidate(text, words, source, variant, *, region=REGION):
    return _build_payload_candidates(
        source, OcrPayload(text, layout_words=tuple(words)), image_key="percent-image",
        image_variant_key=variant, image_transform=(1, 0, 0, 0, 1, 0), image_region=region,
    )[0]


def _readings(*, tilted=False, cotton=95):
    span = 100 - cotton
    source_words = []
    target_words = []
    for material, value, y in (("Cotton", cotton, 30), ("Span", span, 85)):
        number_width = 25 if value >= 10 else 15
        source_words.extend((
            _word(material, 25, y, 90, tilted=tilted),
            _word(f"{value}96", 185, y, number_width + 25, tilted=tilted),
        ))
        target_words.extend((
            _word(material, 25, y, 90, tilted=tilted),
            _word(str(value), 185, y, number_width, tilted=tilted),
            _word("%", 185 + number_width, y, 25, tilted=tilted),
        ))
    original = _candidate(f"Cotton {cotton}96\nSpan {span}96", source_words,
                          "original", "full-input")
    clean_text = f"Cotton {cotton}%\nSpan {span}%"
    first = _candidate(clean_text, target_words, "material_crop", "crop-input", region=CROP_REGION)
    second = _candidate(clean_text, target_words, "material_crop_rotated", "rotated-crop-input",
                        region=CROP_REGION)
    assert original.parser_status == "failed"
    assert first.parser_status == second.parser_status == "success"
    return original, first, second


def _proves(original, alternative, candidates):
    return _percent_glyph_recovery(original, alternative, "generic", "generic", candidates)


def _move(word, dx=0, dy=0):
    return replace(word, left=word.left + dx, right=word.right + dx,
                   top=word.top + dy, bottom=word.bottom + dy,
                   vertices=tuple((x + dx, y + dy) for x, y in word.vertices))


@pytest.mark.parametrize("tilted", [False, True])
def test_two_damaged_percentage_rows_require_two_independent_explicit_rereads(tilted):
    original, first, second = _readings(tilted=tilted)
    candidates = [original, first, second]

    assert not _proves(original, first, [original, first])
    assert not same_region_recovery(original, first, "generic", [original, first])
    assert _proves(original, first, candidates)
    assert _proves(original, second, candidates)
    assert same_region_recovery(original, first, "generic", candidates)
    assert same_region_recovery(original, second, "generic", candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.materials == {"cotton": 95, "spandex": 5}
    assert original.text == "Cotton 9596\nSpan 596"


@pytest.mark.parametrize("cotton", [1, 9, 50, 91, 99])
def test_percent_glyph_recovery_preserves_each_literal_integer_prefix(cotton):
    original, first, second = _readings(cotton=cotton)
    candidates = [original, first, second]

    assert _proves(original, first, candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.materials == {"cotton": cotton, "spandex": 100 - cotton}


def test_percent_glyph_recovery_can_preserve_a_complete_unchanged_percentage_row():
    original, first, second = _readings()
    words = first.image_words[:3] + original.image_words[2:]
    original = _candidate("Cotton 95%\nSpan 596", words, original.source, original.image_variant_key)
    candidates = [original, first, second]

    assert _proves(original, first, candidates)
    assert same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "success"


def test_percent_glyph_recovery_preserves_the_complete_100_percent_prefix():
    original = _candidate("Cotton 10096", (
        _word("Cotton", 25, 30, 90), _word("10096", 185, 30, 65),
    ), "original", "full-input")
    target_words = (
        _word("Cotton", 25, 30, 90), _word("100", 185, 30, 40), _word("%", 225, 30, 25),
    )
    first = _candidate("Cotton 100%", target_words, "material_crop", "crop-input", region=CROP_REGION)
    second = _candidate(first.text, target_words, "material_crop_rotated", "rotated-crop-input",
                        region=CROP_REGION)
    candidates = [original, first, second]

    assert _proves(original, first, candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.materials == {"cotton": 100}


@pytest.mark.parametrize("defect", [
    "same_variant", "same_source", "raw_and_layout", "source_variant_as_supporter",
    "source_variant_as_alternative", "different_image", "missing_variant", "missing_region",
    "different_page", "missing_input", "source_missing_region", "source_missing_source",
    "supporter_missing_source", "source_whitespace_variant", "supporter_whitespace_variant",
])
def test_candidate_records_do_not_supply_independent_crop_confirmation(defect):
    original, first, second = _readings()
    candidates = [original, first, second]
    if defect == "same_variant":
        second = replace(second, image_variant_key=first.image_variant_key)
    elif defect == "same_source":
        second = replace(second, source=first.source)
    elif defect == "raw_and_layout":
        second = replace(first, text="Cotton95%\nSpan5%", layout_used=True)
    elif defect == "source_variant_as_supporter":
        second = replace(second, image_variant_key=original.image_variant_key)
    elif defect == "source_variant_as_alternative":
        first = replace(first, image_variant_key=original.image_variant_key)
    elif defect == "different_image":
        second = replace(second, image_key="unrelated-image")
    elif defect == "missing_variant":
        second = replace(second, image_variant_key="")
    elif defect == "missing_region":
        second = replace(second, image_region=())
    elif defect == "different_page":
        second = replace(second, image_words=tuple(replace(word, page=1) for word in second.image_words))
    elif defect == "source_missing_region":
        original = replace(original, image_region=())
    elif defect == "source_missing_source":
        original = replace(original, source="")
    elif defect == "supporter_missing_source":
        second = replace(second, source="")
    elif defect == "source_whitespace_variant":
        original = replace(original, image_variant_key="   ")
    elif defect == "supporter_whitespace_variant":
        second = replace(second, image_variant_key="   ")
    if defect == "missing_input":
        candidates = [original, first]
    else:
        candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("defect", [
    "inferred_percent", "joined_number_percent", "missing_percent_box", "missing_number_box",
    "missing_material_box", "source_missing_material", "source_missing_number",
    "source_extra_annotation", "target_extra_annotation", "duplicate_source_annotation",
    "duplicate_target_annotation", "source_missing_polygon", "target_missing_polygon",
    "unpaired_target_number", "partial_target_material", "partial_source_number",
])
def test_complete_annotations_and_separate_percent_components_are_required(defect):
    original, first, second = _readings()
    source_words = list(original.image_words)
    target_words = list(first.image_words)
    source_text, target_text = original.text, first.text
    if defect == "inferred_percent":
        target_text = "Cotton 95\nSpan 5"
        target_words = [word for word in target_words if word.text != "%"]
    elif defect == "joined_number_percent":
        target_words = [word for word in target_words if word.text != "%"]
        target_words = [replace(word, text=word.text + "%") if word.text.isdecimal() else word
                        for word in target_words]
    elif defect in {"missing_percent_box", "missing_number_box", "missing_material_box"}:
        missing = {"missing_percent_box": "%", "missing_number_box": "5",
                   "missing_material_box": "Span"}[defect]
        target_words = [word for word in target_words if not (word.top == 85 and word.text == missing)]
    elif defect == "source_missing_material":
        source_words.pop(2)
    elif defect == "source_missing_number":
        source_words.pop(3)
    elif defect == "source_extra_annotation":
        source_words.append(_word("UNKNOWN", 25, 250, 100))
    elif defect == "target_extra_annotation":
        target_words.append(_word("UNKNOWN", 25, 120, 100))
    elif defect == "duplicate_source_annotation":
        source_words.append(source_words[1])
    elif defect == "duplicate_target_annotation":
        target_words.append(target_words[2])
    elif defect == "source_missing_polygon":
        source_words[1] = replace(source_words[1], vertices=())
    elif defect == "target_missing_polygon":
        target_words[2] = replace(target_words[2], vertices=())
    elif defect == "unpaired_target_number":
        target_text = "Cotton 95%\nSpan\n5%"
    elif defect == "partial_target_material":
        target_words[3] = replace(target_words[3], text="Spa")
    elif defect == "partial_source_number":
        source_words[3] = replace(source_words[3], text="59")
    original = _candidate(source_text, source_words, original.source, original.image_variant_key)
    first = _candidate(target_text, target_words, first.source, first.image_variant_key, region=CROP_REGION)
    second = _candidate(target_text, target_words, second.source, second.image_variant_key, region=CROP_REGION)
    candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("defect", [
    "wrong_percent_row", "wrong_number_row", "reused_percent_box", "opposite_direction",
    "reversed_components", "different_coordinate_frame", "outside_source_box",
    "shifted_number_start", "source_outside_crop", "folded_target_row",
])
def test_percent_evidence_keeps_physical_rows_slots_direction_and_source_coordinates(defect):
    original, first, second = _readings()
    source_words = list(original.image_words)
    target_words = list(first.image_words)
    region = CROP_REGION
    if defect == "wrong_percent_row":
        target_words[5] = _move(target_words[5], dy=-55)
    elif defect == "wrong_number_row":
        target_words[4] = _move(target_words[4], dy=-55)
    elif defect == "reused_percent_box":
        target_words[5] = target_words[2]
    elif defect == "opposite_direction":
        points = target_words[5].vertices
        target_words[5] = replace(target_words[5], vertices=(points[1], points[0], points[3], points[2]))
    elif defect == "reversed_components":
        target_words[4] = _move(target_words[4], dx=30)
        target_words[5] = _move(target_words[5], dx=-20)
    elif defect == "different_coordinate_frame":
        target_words = [_move(word, dx=100) for word in target_words]
    elif defect == "outside_source_box":
        target_words[5] = _move(target_words[5], dx=3)
    elif defect == "shifted_number_start":
        target_words[4] = _move(target_words[4], dx=6)
    elif defect == "source_outside_crop":
        region = (120, 0, 500, 160)
    elif defect == "folded_target_row":
        points = target_words[3].vertices
        target_words[3] = replace(target_words[3], vertices=(
            points[0], (points[1][0], points[1][1] + 25),
            (points[2][0], points[2][1] + 25), points[3],
        ), bottom=target_words[3].bottom + 25)
    original = _candidate(original.text, source_words, original.source, original.image_variant_key)
    first = _candidate(first.text, target_words, first.source, first.image_variant_key, region=region)
    second = _candidate(second.text, target_words, second.source, second.image_variant_key, region=region)
    candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("source_number", [
    "595", "599", "596%", "0596", "096", "000596", "10196", "5.96", "59.6", "-596", "+596", "−596",
])
def test_percent_glyph_recovery_does_not_change_other_digits_percentages_decimals_or_signs(source_number):
    original, first, second = _readings()
    source_words = original.image_words[:-1] + (replace(original.image_words[-1], text=source_number),)
    original = _candidate(f"Cotton 9596\nSpan {source_number}", source_words,
                          original.source, original.image_variant_key)
    candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


def test_percent_rereads_cannot_adjust_the_literal_prefixes_to_make_a_total():
    original, first, second = _readings()
    target_words = tuple(replace(word, text="94" if word.text == "95" else "6" if word.text == "5" else word.text)
                         for word in first.image_words)
    first = _candidate("Cotton 94%\nSpan 6%", target_words, first.source,
                       first.image_variant_key, region=CROP_REGION)
    second = _candidate(first.text, target_words, second.source, second.image_variant_key, region=CROP_REGION)
    assert first.parser_status == second.parser_status == "success"
    candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


def test_numeric_percent_proof_does_not_also_change_a_material_annotation():
    original, first, second = _readings()
    words = tuple(replace(word, text="Spandex") if word.text == "Span" else word
                  for word in first.image_words)
    first = _candidate("Cotton 95%\nSpandex 5%", words, first.source, first.image_variant_key,
                       region=CROP_REGION)
    second = _candidate(first.text, words, second.source, second.image_variant_key, region=CROP_REGION)
    assert first.materials == {"cotton": 95, "spandex": 5}
    candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("extra", ["UNKNOWN", "OLEFIN", "FAUX", "CYNTH", "Colo", "L+", "魚", "&"])
@pytest.mark.parametrize("location", ["source_outside_crop", "target"])
def test_percent_agreement_cannot_erase_unknown_or_opaque_surrounding_context(extra, location):
    original, first, second = _readings()
    if location == "source_outside_crop":
        original = _candidate(original.text + "\n" + extra,
                              original.image_words + (_word(extra, 25, 250, 100),),
                              original.source, original.image_variant_key)
    else:
        first = _candidate(first.text + "\n" + extra,
                           first.image_words + (_word(extra, 25, 120, 100),),
                           first.source, first.image_variant_key, region=CROP_REGION)
        second = _candidate(first.text, first.image_words, second.source,
                            second.image_variant_key, region=CROP_REGION)
    candidates = [original, first, second]

    assert not _proves(original, first, candidates)
    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


def test_printed_96_percent_and_real_decimal_percentages_remain_literal_values():
    whole = parse_label("Cotton 96%\nSpan 4%")
    decimal = parse_label("Cotton 99.5%\nSpan 0.5%")

    assert whole["status"] == decimal["status"] == "success"
    assert whole["materials"] == {"cotton": 96, "spandex": 4}
    assert decimal["materials"] == {"cotton": 99.5, "spandex": 0.5}
