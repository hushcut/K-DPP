"""Anchor pruning preserves strict physical row assignments and ambiguity."""

from math import cos, radians, sin

import pytest

from apps.text import ocr_row_search
from apps.text.ocr_geometry import _physical_row, _row_options, _tokens
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_row_search import physical_row_options


def box(text, x, y, width, *, angle=0, height=20):
    theta = radians(angle)
    vertices = tuple((round(px * cos(theta) - py * sin(theta) + 700),
                      round(px * sin(theta) + py * cos(theta) + 700))
                     for px, py in ((x, y), (x + width, y),
                                    (x + width, y + height), (x, y + height)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def unions(options):
    return {frozenset(option) for option in options}


def reference(text, words, *, tokenise=_tokens):
    # The nonphysical search is the independent small-input partition oracle.
    return tuple(option for option in _row_options(text, words, tokenise=tokenise)
                 if _physical_row(text, tuple(words[index] for index in option), tokenise=tokenise))


@pytest.mark.parametrize("angle", [-90, -7, 0, 7, 90, 180])
@pytest.mark.parametrize("number_width,name_width", [(45, 160), (180, 80), (100, 100)])
def test_rotation_and_asymmetric_longest_anchors_match_existing_small_search(angle, number_width, name_width):
    words = (box("55", 20, 100, number_width, angle=angle),
             box("%", 230, 100, 30, angle=angle),
             box("COTTON", 300, 100, name_width, angle=angle))
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == unions(
        reference("55% COTTON", words)) == {frozenset((0, 1, 2))}


@pytest.mark.parametrize("annotations", [
    (("55", 40), ("%", 30), ("COTTON", 160)),
    (("55%", 90), ("COTTON", 160)),
    (("55% COTTON", 300),),
])
def test_combined_annotations_keep_their_original_indices(annotations):
    words = tuple(box(text, 20 + index * 200, 100, width)
                  for index, (text, width) in enumerate(annotations))
    expected = {frozenset(range(len(words)))}
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == expected
    assert expected == unions(reference("55% COTTON", words))


def test_cjk_character_tokeniser_and_joined_annotation_remain_equivalent():
    def characters(text):
        return tuple(character.casefold() for character in text if not character.isspace())

    words = (box("55%", 20, 100, 90), box("聚酯", 150, 100, 90),
             box("纖維", 260, 100, 90), box("55%", 20, 200, 90))
    assert unions(physical_row_options("55% 聚酯纖維", words, tokenise=characters)) == unions(
        reference("55% 聚酯纖維", words, tokenise=characters)) == {frozenset((0, 1, 2))}


def test_projection_ties_do_not_impose_an_input_index_reading_order():
    words = (box("COTTON", 20, 100, 100), box("55", 20, 100, 50), box("%", 20, 100, 30))
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == unions(
        reference("55% COTTON", words)) == {frozenset((0, 1, 2))}


def test_duplicate_annotations_are_distinct_index_assignments():
    word = box("55% COTTON", 20, 100, 300)
    words = (word, word)
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == {
        frozenset((0,)), frozenset((1,)),
    }


def test_two_identical_physical_rows_remain_ambiguous():
    words = tuple(box(text, x, y, width)
                  for y in (100, 200)
                  for text, x, width in (("55", 20, 50), ("%", 90, 30), ("COTTON", 150, 160)))
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == unions(
        reference("55% COTTON", words)) == {frozenset((0, 1, 2)), frozenset((3, 4, 5))}


def test_unused_long_annotation_does_not_force_the_final_anchor():
    words = (box("55", 20, 100, 50), box("%", 90, 100, 30),
             box("COTTON", 150, 100, 160), box("55%", 20, 400, 400))
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == unions(
        reference("55% COTTON", words)) == {frozenset((0, 1, 2))}


def test_repeated_multilingual_ratios_are_pruned_before_partition_budget():
    words = tuple(box(text, x, 100 + language * 100, width)
                  for language, names in enumerate((
                      ("COTTON", "POLYESTER"), ("COTON", "PES"),
                      ("綿", "ポリエステル"), ("면", "폴리에스터")))
                  for text, x, width in (("55", 20, 50), ("%", 85, 30), (names[0], 130, 140),
                                         ("45", 310, 50), ("%", 375, 30), (names[1], 420, 170)))
    text = "55% COTTON 45% POLYESTER"
    assert _row_options(text, words, tokenise=_tokens) == ()
    assert unions(physical_row_options(text, words, tokenise=_tokens)) == {frozenset(range(6))}


def test_identical_anchor_pools_share_one_search(monkeypatch):
    words = (box("55", 20, 100, 100), box("%", 150, 100, 100), box("COTTON", 280, 100, 100))
    monkeypatch.setattr(ocr_row_search, "_MAX_ROW_SEARCH_STATES", 4)
    assert unions(physical_row_options("55% COTTON", words, tokenise=_tokens)) == {frozenset((0, 1, 2))}


def test_budget_is_shared_across_pools_and_never_returns_partial_results(monkeypatch):
    words = tuple(box(text, x, y, width)
                  for y in (100, 200)
                  for text, x, width in (("55", 20, 50), ("%", 90, 30), ("COTTON", 150, 160)))
    assert ocr_row_search._MAX_ROW_SEARCH_STATES == 1024
    monkeypatch.setattr(ocr_row_search, "_MAX_ROW_SEARCH_STATES", 6)
    assert physical_row_options("55% COTTON", words, tokenise=_tokens) == ()


def test_strict_search_does_not_adopt_quantisation_relaxation():
    words = (box("55", 20, 100, 50), box("%", 90, 100, 25, angle=5),
             box("COTTON", 150, 100, 160))
    assert physical_row_options("55% COTTON", words, tokenise=_tokens) == ()


@pytest.mark.parametrize("text", ["55% COTTON", "COTTON 55%", "55% NYLON", "55% COTTON 45% POLYESTER"])
def test_small_mixed_inputs_match_the_unpruned_strict_oracle(text):
    words = (box("55", 20, 100, 50), box("%", 90, 100, 30), box("COTTON", 150, 100, 160),
             box("45", 350, 100, 50), box("%", 420, 100, 30), box("POLYESTER", 480, 100, 180),
             box("55% COTTON", 20, 250, 300))
    assert unions(physical_row_options(text, words, tokenise=_tokens)) == unions(reference(text, words))
