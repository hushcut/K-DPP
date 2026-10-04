"""Only independent complete rereads may prove an attached material separator."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _annotation_tokens, _physical_row, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


REGION = (0, 0, 500, 400)


def _word(text, x, y, width, tilted=False):
    points = ((x, y), (x + width, y), (x + width, y + 12), (x, y + 12))
    if tilted:
        points = tuple((px, py + round(0.1 * px)) for px, py in points)
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), points)


def _candidate(text, words, source, variant):
    return _build_payload_candidates(
        source, OcrPayload(text, layout_words=words), image_key="separator-image",
        image_variant_key=variant, image_transform=(1, 0, 0, 0, 1, 0), image_region=REGION,
    )[0]


def _clean_words(tilted=False, split_percent=False):
    words = []
    for material, number, y in (("POLYESTER", "95", 30), ("POLYURETHANE", "5", 85)):
        words.append(_word(material, 25, y, 140, tilted))
        words.append(_word(number if split_percent else number + "%", 185, y,
                           35 if split_percent else 60, tilted))
        if split_percent:
            words.append(_word("%", 230, y, 15, tilted))
    return tuple(words)


def _readings(tilted=False, source_split_percent=False):
    source_words = (
        _word("POLYESTER", 25, 30, 140, tilted),
        _word("95%", 185, 30, 60, tilted),
        _word("POLYURETHANE.5" if source_split_percent else "POLYURETHANE.5%",
              25, 85, 195 if source_split_percent else 220, tilted),
    )
    if source_split_percent:
        source_words += (_word("%", 230, 85, 15, tilted),)
    original = _candidate("POLYESTER 95%\nPOLYURETHANE.5%", source_words, "original", "full-image")
    first = _candidate("POLYESTER 95%\nPOLYURETHANE 5%", _clean_words(tilted),
                       "material_crop", "crop-input")
    second = _candidate("POLYESTER 95%\nPOLYURETHANE 5%", _clean_words(tilted, True),
                        "material_crop_rotated", "rotated-crop-input")
    assert original.parser_status == "failed"
    assert first.parser_status == second.parser_status == "success"
    return original, first, second


@pytest.mark.parametrize("tilted", [False, True])
@pytest.mark.parametrize("source_split_percent", [False, True])
def test_attached_material_dot_requires_two_explicit_physical_rereads(tilted, source_split_percent):
    original, first, second = _readings(tilted, source_split_percent)
    candidates = [original, first, second]

    assert not same_region_recovery(original, first, "generic", [original, first])
    assert same_region_recovery(original, first, "generic", candidates)
    assert same_region_recovery(original, second, "generic", candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 95, "polyurethane": 5}


@pytest.mark.parametrize("defect", [
    "separated_decimal", "zero_decimal", "two_digits", "numeric_box_only",
    "material_ends_dot", "extra_symbol", "unknown_material", "missing_source_box",
    "missing_target_box", "missing_target_percent_box", "second_number_change", "wrong_target_row",
])
def test_separator_recovery_never_weakens_literal_or_incomplete_evidence(defect):
    original, first, second = _readings()
    source_words = list(original.image_words)
    if defect == "separated_decimal":
        original = replace(original, text="POLYESTER 95%\nPOLYURETHANE .5%")
        source_words[-1] = replace(source_words[-1], text="POLYURETHANE .5%")
    elif defect == "zero_decimal":
        original = replace(original, text="POLYESTER 95%\nPOLYURETHANE0.5%")
        source_words[-1] = replace(source_words[-1], text="POLYURETHANE0.5%")
    elif defect == "two_digits":
        original = replace(original, text="POLYESTER 95%\nPOLYURETHANE.50%")
        source_words[-1] = replace(source_words[-1], text="POLYURETHANE.50%")
    elif defect == "numeric_box_only":
        source_words[-1:] = [_word("POLYURETHANE", 25, 85, 140), _word(".5%", 185, 85, 60)]
    elif defect == "material_ends_dot":
        source_words[-1:] = [_word("POLYURETHANE.", 25, 85, 140), _word("5%", 185, 85, 60)]
    elif defect == "extra_symbol":
        original = replace(original, text="POLYESTER 95%\nPOLYURETHANE.5%魚&")
        source_words[-1] = replace(source_words[-1], text="POLYURETHANE.5%魚&")
    elif defect == "unknown_material":
        original = replace(original, text="POLYESTER 95%\nOLEFIN.5%")
        source_words[-1] = replace(source_words[-1], text="OLEFIN.5%")
    elif defect == "missing_source_box":
        source_words.pop()
    elif defect in {"missing_target_box", "missing_target_percent_box"}:
        missing = "POLYURETHANE" if defect == "missing_target_box" else "%"
        first = replace(first, image_words=tuple(word for word in second.image_words
                                               if not (word.top == 85 and word.text == missing)))
        second = replace(second, image_words=first.image_words)
    elif defect == "second_number_change":
        original = replace(original, text="POLYESTER 5%\nPOLYURETHANE.5%")
        source_words[1] = replace(source_words[1], text="5%")
    elif defect == "wrong_target_row":
        def move_ratio(words):
            return tuple(replace(word, top=30, bottom=42,
                                 vertices=tuple((x, y - 55) for x, y in word.vertices))
                         if word.top == 85 and word.text in {"5", "5%", "%"} else word for word in words)
        first = replace(first, image_words=move_ratio(first.image_words))
        second = replace(second, image_words=move_ratio(second.image_words))
    original = _candidate(original.text, tuple(source_words), original.source, original.image_variant_key)
    assert original.parser_status == "failed"
    candidates = [original, first, second]

    assert not same_region_recovery(original, first, "generic", candidates)
    assert not same_region_recovery(original, second, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("defect", ["same_variant", "same_source", "raw_and_layout", "inferred_percent"])
def test_two_candidate_records_do_not_always_prove_two_independent_integer_readings(defect):
    original, first, second = _readings()
    if defect == "same_variant":
        second = replace(second, image_variant_key=first.image_variant_key)
    elif defect == "same_source":
        second = replace(second, source=first.source)
    elif defect == "raw_and_layout":
        second = replace(first, text="POLYESTER95%\nPOLYURETHANE5%", layout_used=True)
    else:
        second = _candidate("POLYESTER 95\nPOLYURETHANE 5",
                            tuple(replace(word, text=word.text.replace("%", ""))
                                  for word in first.image_words),
                            second.source, second.image_variant_key)
        assert second.parser_status == "success"
    candidates = [original, first, second]

    assert not same_region_recovery(original, first, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


def _polygon_word(text, points):
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), tuple(points))


def _quantised_row(short_token="5"):
    material = _polygon_word("POLYURETHANE", ((25, 85), (165, 92), (165, 104), (25, 97)))
    # A 15px edge rounds a roughly 3-degree slope to either 0px or 1px.
    # The material's 140px edge supplies an independent stable direction.
    number = _polygon_word("5", ((185, 93), (200, 94), (200, 106), (185, 105)))
    percent = _polygon_word("%", ((215, 95), (230, 96), (230, 108), (215, 107)))
    if short_token == "5":
        number = _polygon_word("5", ((185, 93), (200, 93), (200, 106), (185, 105)))
    else:
        percent = _polygon_word("%", ((215, 95), (230, 95), (230, 108), (215, 107)))
    return material, number, percent


@pytest.mark.parametrize("short_token", ["5", "%"])
def test_one_pixel_short_box_rounding_requires_explicit_quantisation_opt_in(short_token):
    words = _quantised_row(short_token)
    assert not _physical_row("POLYURETHANE 5%", words)
    assert _physical_row("POLYURETHANE 5%", words, allow_quantisation=True)


@pytest.mark.parametrize("defect", [
    "top_over_one_pixel", "bottom_over_one_pixel", "opposite_direction", "long_box",
    "wrong_baseline", "multiple_digits", "joined_numeric_percent", "numeric_anchor_only",
])
def test_quantisation_keeps_direction_size_and_baseline_guards(defect):
    material, number, percent = _quantised_row()
    text, words = "POLYURETHANE 5%", (material, number, percent)
    if defect == "top_over_one_pixel":
        number = _polygon_word("5", ((185, 93), (200, 95), (200, 106), (185, 105)))
    elif defect == "bottom_over_one_pixel":
        number = _polygon_word("5", ((185, 93), (200, 93), (200, 108), (185, 105)))
    elif defect == "opposite_direction":
        number = _polygon_word("5", ((200, 93), (185, 93), (185, 106), (200, 105)))
    elif defect == "long_box":
        number = _polygon_word("5", ((185, 93), (218, 93), (218, 107), (185, 105)))
    elif defect == "wrong_baseline":
        number = _polygon_word("5", tuple((x, y + 40) for x, y in number.vertices))
    elif defect == "multiple_digits":
        number = replace(number, text="55")
        text = "POLYURETHANE 55%"
    elif defect == "joined_numeric_percent":
        number = replace(number, text="5%")
        percent = None
    elif defect == "numeric_anchor_only":
        text, words = "5", (number,)
    if defect != "numeric_anchor_only":
        words = (material, number) + ((percent,) if percent is not None else ())

    assert not _physical_row(text, words, allow_quantisation=True)


def test_independent_separator_rereads_can_use_proven_one_pixel_numeric_rounding():
    prefix = (
        _polygon_word("POLYESTER", ((25, 30), (165, 37), (165, 49), (25, 42))),
        _polygon_word("95%", ((185, 38), (245, 41), (245, 53), (185, 50))),
    )
    source_words = prefix + (
        _polygon_word("POLYURETHANE.5%", ((25, 85), (245, 96), (245, 108), (25, 97))),
    )
    first_words = prefix + _quantised_row()
    second_words = prefix + (
        _quantised_row()[0],
        _polygon_word("5%", ((185, 93), (245, 96), (245, 108), (185, 105))),
    )
    original = _candidate("POLYESTER 95%\nPOLYURETHANE.5%", source_words, "original", "full-image")
    first = _candidate("POLYESTER 95%\nPOLYURETHANE 5%", first_words, "material_crop", "crop-input")
    second = _candidate("POLYESTER 95%\nPOLYURETHANE 5%", second_words,
                        "material_crop_rotated", "rotated-crop-input")
    candidates = [original, first, second]

    assert not _physical_row("POLYURETHANE 5%", _quantised_row())
    assert same_region_recovery(original, first, "generic", candidates)
    assert same_region_recovery(original, second, "generic", candidates)
    assert _assess_candidates(candidates).status == "success"


def _country_annotations(joined):
    return ((_word("제조국중국", 25, 250, 150),) if joined else (
        _word("제조국", 25, 250, 90), _word("중국", 125, 250, 60),
    ))


def _with_country(candidate, joined):
    return _candidate(candidate.text + "\n제조국 중국",
                      candidate.image_words + _country_annotations(joined),
                      candidate.source, candidate.image_variant_key)


@pytest.mark.parametrize("case", [
    "source_joined_target_split", "source_split_target_joined", "missing_source_character",
    "added_source_character", "missing_target_character",
])
def test_complete_cjk_metadata_preserves_each_character_during_separator_recovery(case):
    original, first, second = _readings()
    source_joined = case != "source_split_target_joined"
    original = _with_country(original, source_joined)
    first, second = _with_country(first, not source_joined), _with_country(second, not source_joined)
    if case == "missing_source_character":
        original = replace(original, image_words=original.image_words[:-1] + (
            replace(original.image_words[-1], text="제조국중"),
        ))
    elif case == "added_source_character":
        original = replace(original, image_words=original.image_words[:-1] + (
            replace(original.image_words[-1], text="제조국중국산"),
        ))
    elif case == "missing_target_character":
        first = replace(first, image_words=first.image_words[:-1] + (
            replace(first.image_words[-1], text="중"),
        ))
    allowed = case in {"source_joined_target_split", "source_split_target_joined"}
    candidates = [original, first, second]

    assert same_region_recovery(original, first, "generic", candidates) is allowed
    assert same_region_recovery(original, second, "generic", candidates) is allowed
    assert _assess_candidates(candidates).status == ("success" if allowed else "failed")


def test_annotation_character_joining_preserves_ascii_names_numbers_and_signs():
    assert _annotation_tokens("제조국 중국 POLYURETHANE -0.5% +5% 魚&") == (
        "제", "조", "국", "중", "국", "polyurethane", "-", "0", ".", "5", "%", "+", "5", "%", "魚", "&",
    )
    assert _annotation_tokens("POLYURETHANEX") == ("polyurethanex",)
    assert _annotation_tokens("POLYURETHANEX") != _annotation_tokens("POLYURETHANE")
    assert _annotation_tokens("95") != _annotation_tokens("9 5")
    assert _annotation_tokens(".5%") != _annotation_tokens("5%")


@pytest.mark.parametrize("digit", [1, 9])
def test_other_attached_single_digits_keep_exact_independent_integer_ratios(digit):
    original, first, second = _readings()
    polyester = str(100 - digit)
    source_words = tuple(replace(word, text=word.text.replace("95", polyester).replace(".5", f".{digit}"))
                         for word in original.image_words)
    original = _candidate(f"POLYESTER {polyester}%\nPOLYURETHANE.{digit}%", source_words,
                          original.source, original.image_variant_key)
    def clean(candidate):
        words = tuple(replace(word, text=polyester + "%" if word.text == "95%" else polyester if word.text == "95"
                              else str(digit) + "%" if word.text == "5%" else str(digit) if word.text == "5" else word.text)
                      for word in candidate.image_words)
        return _candidate(f"POLYESTER {polyester}%\nPOLYURETHANE {digit}%", words,
                          candidate.source, candidate.image_variant_key)
    first, second = clean(first), clean(second)
    candidates = [original, first, second]

    assert same_region_recovery(original, first, "generic", candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 100 - digit, "polyurethane": digit}


def test_real_decimal_percentages_remain_valid_without_separator_recovery():
    parsed = parse_label("POLYESTER 99.5%\nPOLYURETHANE 0.5%")
    assert parsed["status"] == "success"
    assert parsed["materials"] == {"polyester": 99.5, "polyurethane": 0.5}


@pytest.mark.parametrize("material_row", ["POLYURETHANE.", "POLYURETHANE ."])
def test_inferred_material_end_dot_cannot_change_a_fractional_value(material_row):
    original, first, _second = _readings()
    original = _candidate("POLYESTER95%\nPOLYURETHANE.5%", original.image_words,
                          original.source, original.image_variant_key)
    target_words = tuple(replace(word, text="POLYURETHANE.")
                         if word.text == "POLYURETHANE" else word for word in first.image_words)
    first = _candidate(f"POLYESTER95%\n{material_row}\n5%", target_words,
                       first.source, first.image_variant_key)
    second = replace(first, layout_used=True)
    assert original.parser_status == "failed"
    assert first.parser_status == second.parser_status == "success"
    assert first.materials == {"polyester": 95, "polyurethane": 5}
    candidates = [original, first, second]

    assert not same_region_recovery(original, first, "generic", candidates)
    assert not same_region_recovery(original, second, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("extra", ["OLEFIN", "FAUX", "UNKNOWN", "魚", "&", "魚&"])
def test_separator_recovery_keeps_unexplained_standalone_words(extra):
    original, first, second = _readings()
    original = _candidate(original.text + "\n" + extra,
                          original.image_words + (_word(extra, 25, 250, 100),),
                          original.source, original.image_variant_key)
    assert original.parser_status == "failed"
    candidates = [original, first, second]

    assert not same_region_recovery(original, first, "generic", candidates)
    assert not same_region_recovery(original, second, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"
