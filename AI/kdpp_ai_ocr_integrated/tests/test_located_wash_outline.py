"""Recover a separated care glyph, never a free-standing malformed ratio.

The minimal fixture retains two independent saved Vision responses from one
controlled image-orientation test. It contains only the composition caption,
three fiber rows and the adjacent care band; images and full caches stay local.
"""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from apps.text.ocr_corrections import _same_region_outlined_care_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


_FIXTURE = json.loads((Path(__file__).parent / "fixtures/located_wash_outline.json").read_text(encoding="utf-8"))
_EXPECTED = {"rayon": 68, "polyester": 27, "polyurethane": 5}


def _readings(edit=None):
    fixture = deepcopy(_FIXTURE)
    if edit:
        edit(fixture["responses"])
    candidates = []
    for response in fixture["responses"]:
        words = tuple(OcrWord(**(word | {"vertices": tuple(map(tuple, word["vertices"]))}))
                      for word in response["words"])
        candidates.extend(_build_payload_candidates(
            response["source"], OcrPayload(response["raw"], layout_text=response["layout"], layout_words=words),
            image_key=fixture["case"], image_variant_key=response["source"] + "-response",
            image_transform=(1, 0, 0, 0, 1, 0), image_region=tuple(fixture["image_region"]),
        ))
    return candidates


def _change_word(response, old, new):
    for word in response["words"]:
        if word["text"] == old:
            word["text"] = new
    for key in ("raw", "layout"):
        response[key] = response[key].replace(old, new)


def _move(word, dx=0, dy=0):
    for key in ("left", "right"):
        word[key] += dx
    for key in ("top", "bottom"):
        word[key] += dy
    word["vertices"] = [[x + dx, y + dy] for x, y in word["vertices"]]


def _assert_blocked(candidates):
    for source in candidates[:2]:
        assert not _same_region_outlined_care_recovery(source, candidates[3], "outer", candidates)
    assert _assess_candidates(candidates).status == "failed"


def test_independent_same_location_care_band_preserves_all_three_fiber_ratios():
    candidates = _readings()
    for source in candidates[:2]:
        assert source.parser_status == "failed"
        assert source.rejected_composition_parts == {"outer": ("invalid_composition_evidence",)}
        assert _same_region_outlined_care_recovery(source, candidates[3], "outer", candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.selected_part == "outer"
    assert decision.best.materials == _EXPECTED


@pytest.mark.parametrize("response_indices", [(0,), (1,), (0, 1)])
@pytest.mark.parametrize("move_care_to_ratio_column", [False, True])
def test_fullwidth_percentages_preserve_recovery_and_ratio_column_guard(response_indices, move_care_to_ratio_column):
    def edit(responses):
        fullwidth = str.maketrans("0123456789%", "０１２３４５６７８９％")
        for index in response_indices:
            response = responses[index]
            for text in ("68", "27", "5", "%"):
                _change_word(response, text, text.translate(fullwidth))
        if move_care_to_ratio_column:
            for response in responses:
                for word in response["words"]:
                    if word["text"] in {"1300", "/", "30102", "A"}:
                        _move(word, dx=400)
    candidates = _readings(edit)
    if move_care_to_ratio_column:
        _assert_blocked(candidates)
    else:
        decision = _assess_candidates(candidates)
        assert decision.status == "success"
        assert decision.best.selected_part == "outer"
        assert decision.best.materials == _EXPECTED


@pytest.mark.parametrize("temperature", ["30", "40", "50", "60", "70", "95"])
def test_temperature_grammar_requires_the_same_care_temperature_in_both_reads(temperature):
    def edit(responses):
        _change_word(responses[0], "1300", "1" + temperature + "0")
        _change_word(responses[1], "30102", temperature + "102")
    assert _assess_candidates(_readings(edit)).status == "success"


@pytest.mark.parametrize("text", ["1300%", "-1300", "+1300", "13000", "1310", "10", "30"])
def test_number_spelling_alone_cannot_be_dismissed_as_care(text):
    _assert_blocked(_readings(lambda responses: _change_word(responses[0], "1300", text)))


@pytest.mark.parametrize("text", ["40102", "30102%", "30102FOO", "30", "10"])
def test_metadata_or_another_temperature_is_not_corroboration(text):
    _assert_blocked(_readings(lambda responses: _change_word(responses[1], "30102", text)))


@pytest.mark.parametrize("response_index", [0, 1])
@pytest.mark.parametrize("defect", ["in_composition", "ratio_column", "too_far", "no_direction",
                                  "opposite_direction", "missing_word", "duplicate_word"])
def test_complete_geometry_and_separate_care_location_are_required(response_index, defect):
    def edit(responses):
        response = responses[response_index]
        care = [word for word in response["words"] if word["text"] in {"1300", "/", "30102", "A"}]
        if defect == "in_composition":
            for word in care:
                _move(word, dy=-140)
        elif defect == "ratio_column":
            for word in care:
                _move(word, dx=400)
        elif defect == "too_far":
            for word in care:
                _move(word, dy=350)
        elif defect == "no_direction":
            care[0]["vertices"] = []
        elif defect == "opposite_direction":
            care[0]["vertices"] = care[0]["vertices"][2:] + care[0]["vertices"][:2]
        elif defect == "missing_word":
            response["words"].remove(care[0])
        else:
            response["words"].append(deepcopy(care[0]))
    _assert_blocked(_readings(edit))


@pytest.mark.parametrize("defect", ["printed_a", "missing_a", "opaque_word", "different_glyph"])
def test_an_ordinary_identifier_with_a_small_letter_is_not_a_care_symbol(defect):
    def edit(responses):
        target = responses[1]
        glyph = next(word for word in target["words"] if word["text"] == "A")
        if defect == "printed_a":
            glyph["top"], glyph["bottom"] = 995, 1015
            glyph["vertices"] = [[glyph["left"], 995], [glyph["right"], 995],
                                 [glyph["right"], 1015], [glyph["left"], 1015]]
        elif defect == "missing_a":
            target["words"].remove(glyph)
            target["raw"] = target["raw"].removesuffix("\nA")
            target["layout"] = target["layout"].removesuffix(" A")
        else:
            _change_word(target, "A", "FOO" if defect == "opaque_word" else "B")
    _assert_blocked(_readings(edit))


@pytest.mark.parametrize("response_index", [0, 1])
@pytest.mark.parametrize("old,new", [("68", "69"), ("68", "67"), ("레이온", "면")])
def test_changed_fiber_or_incomplete_total_cannot_be_recovered(response_index, old, new):
    _assert_blocked(_readings(lambda responses: _change_word(responses[response_index], old, new)))


@pytest.mark.parametrize("response_index", [0, 1])
@pytest.mark.parametrize("text", ["10%", "UNKNOWN FIBER", "OLEFIN", "FOO BAR"])
def test_no_intervening_unknown_row_or_second_declaration_may_be_skipped(response_index, text):
    def edit(responses):
        response = responses[response_index]
        # Add a fully boxed row between the last fiber and the care band.
        response["raw"] = response["raw"].replace("5%", "5%\n" + text)
        response["layout"] = response["layout"].replace("5 %", "5 %\n" + text)
        response["words"].insert(-2, {"text": text, "left": 420, "top": 930, "right": 620, "bottom": 950,
                                     "vertices": [[420, 930], [620, 930], [620, 950], [420, 950]], "page": 0})
    _assert_blocked(_readings(edit))


@pytest.mark.parametrize("defect", ["same_variant", "missing_variant", "wrong_image", "missing_region",
                                  "outside_region", "unboxed_raw", "unboxed_layout", "missing_raw_peer"])
def test_independent_response_and_literal_raw_peer_provenance_are_required(defect):
    candidates = _readings()
    if defect == "same_variant":
        candidates[2:] = [replace(c, image_variant_key=candidates[0].image_variant_key) for c in candidates[2:]]
    elif defect == "missing_variant":
        candidates[2:] = [replace(c, image_variant_key="") for c in candidates[2:]]
    elif defect == "wrong_image":
        candidates[2:] = [replace(c, image_key="other-photo") for c in candidates[2:]]
    elif defect == "missing_region":
        candidates[2:] = [replace(c, image_region=()) for c in candidates[2:]]
    elif defect == "outside_region":
        candidates[2:] = [replace(c, image_region=(0, 0, 500, 1440)) for c in candidates[2:]]
    elif defect == "unboxed_raw":
        candidates[0] = replace(candidates[0], text=candidates[0].text + "\nFOO")
    elif defect == "unboxed_layout":
        candidates[1] = replace(candidates[1], text=candidates[1].text + "\nFOO")
    else:
        candidates[1] = replace(candidates[1], source="different-response")
    assert not _same_region_outlined_care_recovery(candidates[0], candidates[3], "outer", candidates)
    assert _assess_candidates(candidates).status == "failed"


def test_the_text_parser_still_rejects_the_unlocated_outline():
    result = parse_label(_FIXTURE["responses"][0]["raw"])
    assert result["status"] == "failed"
    assert result["parse_evidence"]["rejected_composition_parts"] == {"outer": ["invalid_composition_evidence"]}


def test_a_plain_number_without_the_outline_is_not_care():
    def edit(responses):
        response = responses[0]
        response["words"] = [word for word in response["words"] if word["text"] != "/"]
        response["raw"] = response["raw"].removesuffix("/")
        response["layout"] = response["layout"].removesuffix(" /")
    candidates = _readings(edit)
    # Four-digit identifiers already pass the text parser's metadata policy;
    # this recovery must still refuse to reinterpret the number as a care mark.
    for source in candidates[:2]:
        assert not _same_region_outlined_care_recovery(source, candidates[3], "outer", candidates)


@pytest.mark.parametrize("response_index", [0, 1])
def test_the_composition_caption_cannot_be_replaced_by_an_opaque_brand(response_index):
    def edit(responses):
        response = responses[response_index]
        response["raw"] = "BRAND\n" + response["raw"].split("\n", 1)[1]
        response["layout"] = "BRAND\n" + response["layout"].split("\n", 1)[1]
        caption = response["words"][:5]
        response["words"][:5] = [{"text": "BRAND", "left": min(w["left"] for w in caption),
            "top": min(w["top"] for w in caption), "right": max(w["right"] for w in caption),
            "bottom": max(w["bottom"] for w in caption), "vertices": caption[0]["vertices"], "page": 0}]
    _assert_blocked(_readings(edit))


@pytest.mark.parametrize("text", ["10%", "UNKNOWN FIBER", "OLEFIN 5%", "LINING COTTON 100%", "FOO BAR"])
def test_a_later_ratio_or_material_declaration_is_not_hidden_by_the_care_boundary(text):
    def edit(responses):
        source = responses[0]
        for key in ("raw", "layout"):
            source[key] += "\n" + text
        source["words"].append({"text": text, "left": 300, "top": 1100, "right": 650, "bottom": 1125,
                                "vertices": [[300, 1100], [650, 1100], [650, 1125], [300, 1125]], "page": 0})
    candidates = _readings(edit)
    # A valid lower-part declaration may coexist with the established outer
    # policy, but this new recovery must never erase its separate evidence.
    assert not _same_region_outlined_care_recovery(candidates[0], candidates[3], "outer", candidates)
    assert not _same_region_outlined_care_recovery(candidates[1], candidates[3], "outer", candidates)
    if not text.startswith("LINING"):
        assert _assess_candidates(candidates).status == "failed"


def test_a_third_candidate_with_a_different_complete_composition_still_blocks_success():
    candidates = _readings()
    conflicting = _build_payload_candidates("material_crop", OcrPayload("겉감 레이온 60%\n폴리에스터 35%\n폴리우레탄 5%"))
    decision = _assess_candidates(candidates + conflicting)
    assert decision.status == "failed"
    assert "outer" in decision.conflicting_parts
