"""A reread may release rejection only after locating the complete source text."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _evidence_rows, _row_words, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def word(text, x, y=10):
    return OcrWord(text, x, y, x + 100, y + 20)


def candidates(text, words, source="original"):
    return _build_payload_candidates(
        source, OcrPayload(text, layout_words=words), image_key="same-image",
        image_variant_key=source, image_transform=(1, 0, 0, 0, 1, 0),
        image_region=(0, 0, 600, 400),
    )


@pytest.mark.parametrize("missing", ["OLEFIN", "FAUX", "UNKNOWN", "MODACRYLIC"])
def test_crop_cannot_erase_unlocated_unknown_or_negating_material(missing):
    source_words = (word("Cotton", 10), word("90%", 300), word("10%", 300, 50))
    target_words = source_words + (word("Polyester", 10, 50),)
    original = candidates(f"Cotton 90%\n{missing} 10%", source_words)
    corrected = candidates("Cotton 90%\nPolyester 10%", target_words, "material_crop")

    assert _row_words(f"{missing} 10%", source_words) == ()
    assert not same_region_recovery(original[0], corrected[0], "generic")
    assert _assess_candidates(original + corrected).status == "failed"


@pytest.mark.parametrize("missing", ["Polgester", "75", "%"])
@pytest.mark.parametrize("missing_from", ["original", "corrected"])
def test_source_and_target_both_require_material_number_and_percent_boxes(missing, missing_from):
    source_words = (
        word("Polgester", 10), word("75", 300), word("%", 400),
        word("Rayon", 10, 50), word("21%", 300, 50),
        word("Span", 10, 90), word("4%", 300, 90),
    )
    target_words = (replace(source_words[0], text="Polyester"),) + source_words[1:]
    if missing_from == "original":
        source_words = tuple(item for item in source_words if item.text != missing)
    else:
        target_token = "Polyester" if missing == "Polgester" else missing
        target_words = tuple(item for item in target_words if item.text != target_token)

    original = candidates("Polgester 75%\nRayon 21%\nSpan 4%", source_words)
    corrected = candidates("Polyester 75%\nRayon 21%\nSpan 4%", target_words, "material_crop")
    assert not same_region_recovery(original[0], corrected[0], "generic")
    assert _assess_candidates(original + corrected).status == "failed"


@pytest.mark.parametrize("text, boxes", [
    ("Cotton -5%", ("Cotton", "5%")),
    ("Cotton +5%", ("Cotton", "5%")),
    ("Cotton −5%", ("Cotton", "5%")),
    ("Cotton 5.5%", ("Cotton", "5", "5", "%")),
    ("Cotton 5% X", ("Cotton", "5%")),
    ("FAUX Cotton 5%", ("Cotton", "5%")),
    ("Cotton Cotton 5%", ("Cotton", "5%")),
    ("Cotton 5%%", ("Cotton", "5%")),
    ("Cotton 5%", ("Cot", "5%")),
    ("Cotton 5%", ("Cotton", "Cotton", "5%")),
    ("Cotton 5%", ("Cotton 5%", "5%")),
])
def test_missing_partial_and_duplicate_tokens_never_locate_a_complete_row(text, boxes):
    assert _row_words(text, tuple(word(token, index * 110) for index, token in enumerate(boxes))) == ()


def test_equal_token_counts_do_not_allow_overlapping_text_spans():
    boxes = (word("Cotton 50%", 10), word("50% Polyester", 200))
    assert _row_words("Cotton 50% Polyester 50%", boxes) == ()


def test_long_repeated_and_overlapping_annotations_remain_unconfirmed():
    # All totals match, but the 79 leading tokens needed before "a b a"
    # cannot be covered by the even-length boxes. Different box orders must
    # not cause unbounded combinatorial work to release this uncertainty.
    text = " ".join(["a"] * 80 + ["b"] + ["a"] * 79 + ["c"])
    boxes = tuple(word(" ".join(["a"] * length), 10) for length in range(2, 25, 2))
    boxes += (word("a b a", 10), word("a c", 10))
    assert _row_words(text, boxes) == ()


def test_long_unambiguous_annotations_still_have_complete_coverage():
    tokens = [f"fiber{index}" for index in range(80)]
    boxes = tuple(word(token, 10) for token in tokens)
    assert _row_words(" ".join(tokens), boxes) == boxes


@pytest.mark.parametrize("text, boxes", [
    ("Polyester75%", ("Polyester", "75", "%")),
    ("Polyester 75%", ("Polyester75%",)),
    ("Polyester 75%", ("Polyester", "75%")),
    ("면７５％", ("면", "75", "%")),
    ("Polgester 75%", ("Polgester", "75%")),
    ("Cotton -5%", ("Cotton", "-", "5", "%")),
    ("Cotton 5.5%", ("Cotton", "5", ".", "5", "%")),
    ("Cotton 50% Polyester 50%", ("Cotton 50%", "Polyester 50%")),
])
def test_complete_boxes_keep_joined_split_and_normalized_token_coverage(text, boxes):
    image_words = tuple(word(token, index * 110) for index, token in enumerate(boxes))
    assert _row_words(text, image_words) == image_words


def test_isolated_percent_stays_locatable_but_cannot_be_reused_by_two_rows():
    image_words = (word("polyester", 10), word("%", 300, 100))
    original = candidates("polyester\n%\n%", image_words)[0]
    assert _row_words("%", image_words) == (image_words[1],)
    assert _evidence_rows(original, "generic") == []


@pytest.mark.parametrize("split_percent", [False, True])
def test_complete_geometry_preserves_literal_dropped_digit_recovery(split_percent):
    source_words, target_words = [], []
    for material, raw_number, target_number, y in (
        ("Polyester", "5", "75", 10), ("Rayon", "21", "21", 50), ("Span", "4", "4", 90),
    ):
        for collection, number in ((source_words, raw_number), (target_words, target_number)):
            collection.append(word(material, 10, y))
            collection.append(word(number if split_percent else number + "%", 300, y))
            if split_percent:
                collection.append(word("%", 350, y))
    original = candidates("Polyester5%\nRayon21%\nSpan4%", tuple(source_words))
    corrected = candidates("Polyester75%\nRayon21%\nSpan4%", tuple(target_words), "material_crop")
    decision = _assess_candidates(original + corrected)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 75, "rayon": 21, "spandex": 4}
