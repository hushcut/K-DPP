"""A complete spatial assignment must retain every repeated composition row."""

from dataclasses import replace
import math

import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text.ocr_corrections import _evidence_rows, _row_words, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import (
    OcrMetadata, OcrPayload, OcrResult, _assess_candidates, _build_payload_candidates,
)


REGION = (0, 0, 600, 600)
ORIENTATIONS = ("horizontal", "tilted", "clockwise", "counterclockwise")


def _word(text, x, y, width=90, orientation="horizontal", page=0):
    points = ((x, y), (x + width, y), (x + width, y + 12), (x, y + 12))
    if orientation == "tilted":
        points = tuple((px, py + round(0.12 * px)) for px, py in points)
    elif orientation == "clockwise":
        points = tuple((450 - py, px) for px, py in points)
    elif orientation == "counterclockwise":
        points = tuple((py, 450 - px) for px, py in points)
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), points, page)


def _boxes(rows, orientation="horizontal", segmentation="joined_percent"):
    words, cohorts = [], []
    for index, (material, number) in enumerate(rows):
        y = 30 + index * 55
        if segmentation == "whole_row":
            cohort = (_word(f"{material} {number}%", 25, y, 230, orientation),)
        elif segmentation == "split_percent":
            cohort = (
                _word(material, 25, y, 110, orientation),
                _word(str(number), 185, y, 35, orientation),
                _word("%", 230, y, 15, orientation),
            )
        else:
            cohort = (
                _word(material, 25, y, 110, orientation),
                _word(f"{number}%", 185, y, 60, orientation),
            )
        words.extend(cohort)
        cohorts.append(frozenset(cohort))
    return tuple(words), tuple(cohorts)


def _candidate(text, words, source="original"):
    return _build_payload_candidates(
        source, OcrPayload(text, layout_words=words), image_key="row-assignment-image",
        image_variant_key=source, image_transform=(1, 0, 0, 0, 1, 0),
        image_region=REGION,
    )[0]


def _text(rows):
    return "\n".join(f"{material} {number}%" for material, number in rows)


def _assert_complete_rows(candidate, cohorts):
    rows = _evidence_rows(candidate, "generic")
    assert len(rows) == len(cohorts)
    actual = tuple(frozenset(words) for _info, words in rows)
    assert set(actual) == set(cohorts)
    assert sum(map(len, actual)) == len(set().union(*actual))
    assert set().union(*actual) == set(candidate.image_words)


def _response(decision):
    return analyze_ocr_result(OcrResult(
        decision.best.text,
        OcrMetadata(
            source=decision.best.source, confidence="medium", candidate_count=2,
            image_format="PNG", width=600, height=600,
            conflicting_parts=decision.conflicting_parts,
            unpaired_ratio_parts=decision.unpaired_ratio_parts,
            rejected_composition_parts=decision.rejected_composition_parts,
        ),
    ))


@pytest.mark.parametrize("orientation", ORIENTATIONS)
@pytest.mark.parametrize("segmentation", ["joined_percent", "split_percent", "whole_row"])
@pytest.mark.parametrize("reversed_boxes", [False, True])
def test_repeated_complete_rows_are_located_without_reusing_boxes(
    orientation, segmentation, reversed_boxes,
):
    readings = (("POLYESTER", 100), ("POLYESTER", 100))
    words, cohorts = _boxes(readings, orientation, segmentation)
    if reversed_boxes:
        words = tuple(reversed(words))
    original = _candidate(_text(readings), words)
    reread = _candidate(_text(readings), words, "material_crop")

    _assert_complete_rows(original, cohorts)
    _assert_complete_rows(reread, cohorts)
    assert same_region_recovery(original, reread, "generic")
    assert _assess_candidates([original, reread]).best.materials == {"polyester": 100}


@pytest.mark.parametrize("orientation", ORIENTATIONS)
@pytest.mark.parametrize("source_segmentation,target_segmentation", [
    ("joined_percent", "whole_row"), ("split_percent", "whole_row"),
    ("whole_row", "joined_percent"), ("whole_row", "split_percent"),
])
def test_complete_repeated_rows_keep_rereads_with_joined_or_split_row_boxes(
    orientation, source_segmentation, target_segmentation,
):
    readings = (("POLYESTER", 100), ("POLYESTER", 100))
    source_words, source_cohorts = _boxes(readings, orientation, source_segmentation)
    target_words, target_cohorts = _boxes(readings, orientation, target_segmentation)
    original = _candidate(_text(readings), source_words)
    reread = _candidate(_text(readings), target_words, "material_crop")

    _assert_complete_rows(original, source_cohorts)
    _assert_complete_rows(reread, target_cohorts)
    assert same_region_recovery(original, reread, "generic")


@pytest.mark.parametrize("orientation", ORIENTATIONS)
def test_ratio_first_rows_keep_the_physical_reading_order(orientation):
    words = tuple(
        _word(token, x, y, width, orientation)
        for y in (30, 85)
        for token, x, width in (("100", 25, 35), ("%", 70, 15), ("POLYESTER", 105, 110))
    )
    cohorts = tuple(frozenset(words[index:index + 3]) for index in (0, 3))
    original = _candidate("100% POLYESTER\n100% POLYESTER", tuple(reversed(words)))
    reread = _candidate("100% POLYESTER\n100% POLYESTER", words, "material_crop")

    _assert_complete_rows(original, cohorts)
    _assert_complete_rows(reread, cohorts)
    assert same_region_recovery(original, reread, "generic")


@pytest.mark.parametrize("orientation", ORIENTATIONS)
@pytest.mark.parametrize("source_segmentation", ["joined_percent", "split_percent"])
@pytest.mark.parametrize("target_segmentation", ["joined_percent", "split_percent"])
def test_shared_ratios_and_percent_boxes_keep_dropped_digit_recovery(
    orientation, source_segmentation, target_segmentation,
):
    original_rows = (("POLYESTER", 5), ("RAYON", 25), ("SPAN", 25), ("COTTON", 25))
    corrected_rows = (("POLYESTER", 25), ("RAYON", 25), ("SPAN", 25), ("COTTON", 25))
    source_words, source_cohorts = _boxes(original_rows, orientation, source_segmentation)
    target_words, target_cohorts = _boxes(corrected_rows, orientation, target_segmentation)
    original = _candidate(_text(original_rows), tuple(reversed(source_words)))
    reread = _candidate(_text(corrected_rows), target_words, "material_crop")

    _assert_complete_rows(original, source_cohorts)
    _assert_complete_rows(reread, target_cohorts)
    assert original.parser_status == "failed"
    assert reread.parser_status == "success"
    assert same_region_recovery(original, reread, "generic")
    decision = _assess_candidates([original, reread])
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 25, "rayon": 25, "spandex": 25, "cotton": 25}


@pytest.mark.parametrize("segmentation", ["joined_percent", "split_percent", "whole_row"])
def test_single_row_lookup_cannot_guess_between_repeated_physical_rows(segmentation):
    words, _cohorts = _boxes((("POLYESTER", 100), ("POLYESTER", 100)), segmentation=segmentation)
    assert _row_words("POLYESTER 100%", words) == ()


@pytest.mark.parametrize("orientation", ORIENTATIONS)
@pytest.mark.parametrize("extra_rows", [1, 2])
def test_unreported_identical_physical_rows_make_assignment_ambiguous(orientation, extra_rows):
    readings = (("POLYESTER", 100), ("POLYESTER", 100))
    words, _cohorts = _boxes(readings + (("POLYESTER", 100),) * extra_rows, orientation)
    original = _candidate(_text(readings), words)
    reread_words, _ = _boxes(readings, orientation)
    reread = _candidate(_text(readings), reread_words, "material_crop")

    assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")


@pytest.mark.parametrize("missing", ["POLYESTER", "100%", "RAYON", "25", "%"])
def test_missing_repeated_row_box_does_not_release_source_rejection(missing):
    readings = (("POLYESTER", 25), ("RAYON", 25), ("SPAN", 25), ("COTTON", 25))
    words, _cohorts = _boxes(readings, segmentation="split_percent")
    if missing == "100%":
        readings = (("POLYESTER", 100), ("POLYESTER", 100))
        words, _cohorts = _boxes(readings)
    index = next(index for index, word in enumerate(words) if word.text == missing)
    incomplete = words[:index] + words[index + 1:]
    original = _candidate(_text(readings), incomplete)
    reread = _candidate(_text(readings), words, "material_crop")

    assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")


@pytest.mark.parametrize("bad_material", ["OLEFIN", "FAUX", "UNKNOWN", "MODACRYLIC"])
@pytest.mark.parametrize("located", [False, True])
def test_repeated_ratio_assignment_cannot_erase_unknown_or_negating_material(bad_material, located):
    source_rows = (("COTTON", 50), (bad_material, 50))
    target_rows = (("COTTON", 50), ("POLYESTER", 50))
    source_words, _cohorts = _boxes(source_rows)
    if not located:
        source_words = tuple(word for word in source_words if word.text != bad_material)
    target_words, _ = _boxes(target_rows)
    original = _candidate(_text(source_rows), source_words)
    reread = _candidate(_text(target_rows), target_words, "material_crop")

    if not located:
        assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")
    assert _assess_candidates([original, reread]).status == "failed"


@pytest.mark.parametrize("duplicate_count", [1, 2])
def test_same_physical_boxes_cannot_satisfy_multiple_text_rows(duplicate_count):
    words, _cohorts = _boxes((("POLYESTER", 100),))
    original = _candidate("POLYESTER 100%\nPOLYESTER 100%", words * duplicate_count)
    target_words, _ = _boxes((("POLYESTER", 100), ("POLYESTER", 100)))
    reread = _candidate("POLYESTER 100%\nPOLYESTER 100%", target_words, "material_crop")

    assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")


@pytest.mark.parametrize("extra", ["7", "+", "-", "X", "FAUX"])
def test_unlocated_extra_numeric_or_modifier_token_keeps_complete_row_required(extra):
    rows = (("COTTON", 50), ("POLYESTER", 50))
    words, _cohorts = _boxes(rows)
    original = _candidate(f"COTTON 50% {extra}\nPOLYESTER 50%", words)
    reread = _candidate(_text(rows), words, "material_crop")

    assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")


def test_equal_token_counts_with_overlapping_spans_cannot_form_spatial_rows():
    words = (
        _word("COTTON 50%", 25, 30, 180),
        _word("50% POLYESTER", 230, 30, 180),
    )
    original = _candidate("COTTON 50% POLYESTER 50%", words)
    target_words, _ = _boxes((("COTTON", 50), ("POLYESTER", 50)))
    reread = _candidate("COTTON 50%\nPOLYESTER 50%", target_words, "material_crop")

    assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")


@pytest.mark.parametrize("orientation", ORIENTATIONS)
def test_global_token_totals_cannot_validate_swapped_material_ratios(orientation):
    physical_rows = (("COTTON", 20), ("POLYESTER", 80))
    words, _cohorts = _boxes(physical_rows, orientation)
    original = _candidate("COTTON 80%\nPOLYESTER 20%", words)
    reread = _candidate(_text(physical_rows), words, "material_crop")

    assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")
    decision = _assess_candidates([original, reread])
    assert decision.status == "failed"
    response = _response(decision)
    assert response["status"] == "failed"
    assert response["materials"] == {}


@pytest.mark.parametrize("fold", ["opposite_tilt", "opposite_quarter_turn"])
def test_opposite_folds_cannot_release_a_successful_swapped_raw_reading(fold):
    physical_rows = (("COTTON", 20), ("POLYESTER", 80))
    orientation = "tilted" if fold == "opposite_tilt" else "clockwise"
    words, _ = _boxes(physical_rows, orientation)
    adjusted = list(words)
    if fold == "opposite_quarter_turn":
        opposite, _ = _boxes(physical_rows, "counterclockwise")
        adjusted[-2:] = opposite[-2:]
    else:
        for index in range(2, len(adjusted)):
            item = adjusted[index]
            points = tuple((px, py - 2 * round(0.12 * px)) for px, py in item.vertices)
            xs, ys = zip(*points)
            adjusted[index] = replace(item, top=min(ys), bottom=max(ys), vertices=points)
    original = _candidate("COTTON 80%\nPOLYESTER 20%", tuple(adjusted))
    reread = _candidate(_text(physical_rows), tuple(adjusted), "material_crop")

    assert original.parser_status == "success"
    assert not same_region_recovery(original, reread, "generic")
    assert _assess_candidates([original, reread]).status == "failed"


@pytest.mark.parametrize("defect", ["opposite_tilt", "opposite_quarter_turn", "incomplete_vertices", "degenerate_vertices"])
def test_unproved_mixed_orientation_does_not_resolve_repeated_rows(defect):
    readings = (("POLYESTER", 100), ("POLYESTER", 100))
    orientation = "clockwise" if defect == "opposite_quarter_turn" else "tilted"
    words, _cohorts = _boxes(readings, orientation)
    adjusted = list(words)
    if defect == "opposite_quarter_turn":
        opposite, _ = _boxes(readings, "counterclockwise")
        adjusted[-2:] = opposite[-2:]
    elif defect == "opposite_tilt":
        for index in range(2, len(adjusted)):
            item = adjusted[index]
            points = tuple((px, py - 2 * round(0.12 * px)) for px, py in item.vertices)
            xs, ys = zip(*points)
            adjusted[index] = replace(item, top=min(ys), bottom=max(ys), vertices=points)
    elif defect == "incomplete_vertices":
        adjusted[0] = replace(adjusted[0], vertices=adjusted[0].vertices[:3])
    else:
        point = adjusted[0].vertices[0]
        adjusted[0] = replace(adjusted[0], vertices=(point,) * 4)
    original = _candidate(_text(readings), tuple(adjusted))
    reread_words, _ = _boxes(readings, orientation)
    reread = _candidate(_text(readings), reread_words, "material_crop")

    if defect in {"incomplete_vertices", "degenerate_vertices"}:
        assert _evidence_rows(original, "generic") == []
    assert not same_region_recovery(original, reread, "generic")


def test_two_pages_do_not_share_repeated_row_assignment():
    readings = (("POLYESTER", 100), ("POLYESTER", 100))
    words, _cohorts = _boxes(readings)
    mixed = words[:2] + tuple(replace(word, page=1) for word in words[2:])
    original = _candidate(_text(readings), mixed)
    reread = _candidate(_text(readings), words, "material_crop")

    for _info, row_words in _evidence_rows(original, "generic"):
        assert len({word.page for word in row_words}) == 1
    assert not same_region_recovery(original, reread, "generic")


def _origin_words(orientation):
    prefix = tuple(
        _word(token, x, 260, width, orientation)
        for token, x, width in (("MADE", 25, 45), ("IN", 80, 20), ("SRI", 110, 30))
    )
    angle = math.radians(114 if orientation == "clockwise" else -114)
    points = tuple(
        (round(360 + math.cos(angle) * x - math.sin(angle) * y),
         round(280 + math.sin(angle) * x + math.cos(angle) * y))
        for x, y in ((0, 0), (90, 0), (90, 12), (0, 12))
    )
    xs, ys = zip(*points)
    return prefix + (OcrWord("LANKA", min(xs), min(ys), max(xs), max(ys), points),)


def _origin_bridge(orientation="clockwise", segmentation="joined_percent"):
    readings = (("POLYESTER", 100), ("POLYESTER", 100))
    core, cohorts = _boxes(readings, orientation, segmentation)
    words = core + _origin_words(orientation)
    raw = _text(readings) + "\nMADE IN SRI LANKA"
    mixed = "POLYESTER\n100% LANKA\nPOLYESTER\n100%\nMADE IN SRI"
    candidates = _build_payload_candidates(
        "original", OcrPayload(raw, mixed, layout_words=words),
        image_key="origin-bridge-image", image_variant_key="original",
        image_transform=(1, 0, 0, 0, 1, 0), image_region=REGION,
    )
    assert len(candidates) == 2
    target, broken = candidates
    assert target.parser_status == "success"
    assert broken.parser_status == "failed"
    assert broken.layout_used
    return target, broken, cohorts


@pytest.mark.parametrize("orientation", ["clockwise", "counterclockwise"])
@pytest.mark.parametrize("segmentation", ["joined_percent", "split_percent"])
def test_preserved_origin_metadata_can_bridge_a_broken_rotated_layout(orientation, segmentation):
    target, broken, cohorts = _origin_bridge(orientation, segmentation)
    rows = _evidence_rows(target, "generic")
    assert set(frozenset(words) for _info, words in rows) == set(cohorts)
    assert same_region_recovery(broken, target, "generic", [target, broken])
    decision = _assess_candidates([target, broken])
    assert decision.status == "success"
    assert _response(decision)["materials"] == {"polyester": 100}


@pytest.mark.parametrize("defect", [
    "missing_source_origin_box", "missing_target_origin_box", "missing_target_origin_text",
    "changed_target_origin_text", "changed_source_origin_text", "unlocated_OLEFIN", "unlocated_FAUX",
])
def test_origin_bridge_cannot_discard_missing_or_changed_context(defect):
    target, broken, _cohorts = _origin_bridge()
    if defect == "missing_source_origin_box":
        broken = replace(broken, image_words=tuple(word for word in broken.image_words if word.text != "LANKA"))
    elif defect == "missing_target_origin_box":
        target = replace(target, image_words=tuple(word for word in target.image_words if word.text != "LANKA"))
    elif defect == "missing_target_origin_text":
        target = replace(target, text=target.text.replace("\nMADE IN SRI LANKA", ""))
    elif defect == "changed_target_origin_text":
        target = replace(
            target, text=target.text.replace("LANKA", "LANXA"),
            image_words=tuple(replace(word, text="LANXA") if word.text == "LANKA" else word for word in target.image_words),
        )
    elif defect == "changed_source_origin_text":
        broken = replace(broken, text=broken.text.replace("LANKA", "LANXA"))
    else:
        bad_material = defect.removeprefix("unlocated_")
        broken = replace(broken, text=broken.text + f"\n{bad_material} 5%")

    assert not same_region_recovery(broken, target, "generic", [target, broken])
    decision = _assess_candidates([target, broken])
    assert decision.status == "failed"
    assert _response(decision)["materials"] == {}


@pytest.mark.parametrize("fold", ["none", "opposite_tilt", "opposite_quarter_turn"])
def test_preserved_origin_context_cannot_erase_swapped_successful_raw_ratios(fold):
    orientation = "tilted" if fold == "opposite_tilt" else "clockwise"
    readings = (("COTTON", 20), ("POLYESTER", 80))
    core, _ = _boxes(readings, orientation)
    adjusted = list(core)
    if fold == "opposite_quarter_turn":
        opposite, _ = _boxes(readings, "counterclockwise")
        adjusted[-2:] = opposite[-2:]
    elif fold == "opposite_tilt":
        for index in range(2, len(adjusted)):
            item = adjusted[index]
            points = tuple((px, py - 2 * round(0.12 * px)) for px, py in item.vertices)
            xs, ys = zip(*points)
            adjusted[index] = replace(item, top=min(ys), bottom=max(ys), vertices=points)
    words = tuple(adjusted) + _origin_words("clockwise")
    original = _candidate("COTTON 80%\nPOLYESTER 20%\nMADE IN SRI LANKA", words)
    corrected = _candidate(_text(readings) + "\nMADE IN SRI LANKA", words, "material_crop")
    mixed = _candidate("COTTON\n20% LANKA\nPOLYESTER\n80%\nMADE IN SRI", words)
    mixed = replace(mixed, layout_used=True)

    assert original.parser_status == corrected.parser_status == "success"
    assert not same_region_recovery(original, corrected, "generic", [original, mixed, corrected])
    decision = _assess_candidates([original, mixed, corrected])
    assert decision.status == "failed"
    assert _response(decision)["materials"] == {}


@pytest.mark.parametrize("damaged_ratio", [".5%", ".5%魚", ".5%魚&"])
def test_row_linking_does_not_restore_unproved_decimal_or_symbol_damage(damaged_ratio):
    rows = (("POLYESTER", 5), ("RAYON", 95))
    words, _ = _boxes(rows)
    source_words = tuple(replace(word, text=damaged_ratio) if word.text == "5%" else word for word in words)
    original = _candidate(f"POLYESTER {damaged_ratio}\nRAYON 95%", source_words)
    corrected = _candidate(_text(rows), words, "material_crop")

    assert not same_region_recovery(original, corrected, "generic")
    assert _assess_candidates([original, corrected]).status == "failed"


@pytest.mark.parametrize("segmentation", ["joined_percent", "split_percent"])
def test_additional_overlapping_ratio_cannot_reuse_one_target_reading(segmentation):
    readings = (("POLYESTER", 95), ("POLYURETHANE", 5))
    core, _ = _boxes(readings, segmentation=segmentation)
    extra_tokens = ("5%",) if segmentation == "joined_percent" else ("5", "%")
    duplicate = tuple(
        replace(
            word, left=word.left + 1, top=word.top + 1,
            right=word.right + 1, bottom=word.bottom + 1,
            vertices=tuple((x + 1, y + 1) for x, y in word.vertices),
        )
        for word in core[-2:] if word.text in extra_tokens
    )
    original = _candidate(_text(readings) + "\n5%", core + duplicate)
    corrected = _candidate(_text(readings), core, "material_crop")

    assert original.parser_status == "failed"
    assert corrected.parser_status == "success"
    assert not same_region_recovery(original, corrected, "generic")
    decision = _assess_candidates([original, corrected])
    assert decision.status == "failed"
    assert _response(decision)["materials"] == {}
