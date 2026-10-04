"""A complete literal raw peer may prove a failed layout from its own response."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _evidence_rows, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def _word(text, x, y, width, height):
    points = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return OcrWord(text, x, y, x + width, y + height, points)


def _candidates(*, ratio="5", metadata_count=12, extra="", target_ratio="75"):
    # The neighbouring separate percent boxes defeat the layout row's local
    # selection. Joined CJK metadata then defeats the legacy global tokenizer;
    # every character still has an annotation for the literal raw-peer proof.
    words = (
        _word("Polyester", 100, 100, 140, 30), _word("Rayon", 100, 145, 100, 28),
        _word("Span", 100, 187, 75, 27), _word(ratio, 350, 105, 25, 20),
        _word("%", 378, 105, 20, 20), _word("21", 345, 142, 30, 22),
        _word("%", 378, 142, 20, 22), _word("4", 350, 182, 20, 19),
        _word("%", 378, 182, 20, 19),
    )
    words += tuple(word for index in range(metadata_count) for word in (
        _word("제조국", 100, 300 + 28 * index, 90, 20),
        _word("중국", 200, 300 + 28 * index, 60, 20),
    ))
    raw = f"Polyester\nRayon\nSpan\n{ratio}%\n21%\n4%"
    layout = f"Polyester {ratio}%\nRayon 21%\nSpan 4%"
    raw += "\n제조국 중국" * metadata_count
    layout += "\n제조국중국" * metadata_count
    if extra:
        raw += "\n" + extra
        layout += "\n" + extra
        words += (_word(extra, 100, 250, 150, 20),)
    readings = _build_payload_candidates(
        "original", OcrPayload(raw, layout_text=layout, layout_words=words),
        image_key="same-photo", image_variant_key="same-response-input",
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 800, 1000),
    )
    assert len(readings) == 2
    raw, layout = readings
    target_words = tuple(_word(text, x, y, width, height) for text, x, y, width, height in (
        ("Polyester", 100, 100, 140, 30), (target_ratio + "%", 345, 105, 60, 20),
        ("Rayon", 100, 145, 100, 28), ("21%", 345, 142, 60, 22),
        ("Span", 100, 187, 75, 27), ("4%", 350, 182, 55, 19),
    ))
    target = _build_payload_candidates(
        "material_crop_rotated", OcrPayload(f"Polyester {target_ratio}%\nRayon 21%\nSpan 4%",
                                           layout_words=target_words),
        image_key="same-photo", image_variant_key="physical-crop-input",
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(80, 80, 430, 245),
    )[0]
    return raw, layout, target


@pytest.mark.parametrize("metadata_count", [1, 12, 24])
def test_literal_raw_peer_preserves_long_repeated_metadata_when_layout_cannot_locate_rows(metadata_count):
    raw, layout, target = _candidates(metadata_count=metadata_count)
    candidates = [raw, layout, target]
    assert raw.rejected_composition_parts == layout.rejected_composition_parts == {
        "generic": ("unpaired_material_rows",),
    }
    assert _evidence_rows(raw, "generic")
    assert not _evidence_rows(layout, "generic")
    assert same_region_recovery(raw, target, "generic", candidates)
    assert not same_region_recovery(layout, target, "generic", [layout, target])
    assert same_region_recovery(layout, target, "generic", candidates)
    decision = _assess_candidates(candidates)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 75, "rayon": 21, "spandex": 4}


@pytest.mark.parametrize("defect", ["source", "variant", "image", "region", "word_text", "word_geometry",
                                   "missing_word", "layout_peer", "successful_peer", "peer_reason", "layout_reason"])
def test_raw_peer_requires_the_exact_same_response_provenance_and_rejection(defect):
    raw, layout, target = _candidates()
    if defect == "source":
        raw = replace(raw, source="preprocessed")
    elif defect == "variant":
        raw = replace(raw, image_variant_key="different-input")
    elif defect == "image":
        raw = replace(raw, image_key="different-photo")
    elif defect == "region":
        raw = replace(raw, image_region=(0, 0, 801, 1000))
    elif defect == "word_text":
        raw = replace(raw, image_words=(replace(raw.image_words[0], text="OLEFIN"),) + raw.image_words[1:])
    elif defect == "word_geometry":
        raw = replace(raw, image_words=(replace(raw.image_words[0], left=101),) + raw.image_words[1:])
    elif defect == "missing_word":
        raw = replace(raw, image_words=raw.image_words[:-1])
    elif defect == "layout_peer":
        raw = replace(raw, layout_used=True)
    elif defect == "successful_peer":
        raw = replace(raw, parser_status="success")
    elif defect == "peer_reason":
        raw = replace(raw, rejected_composition_parts={"generic": ("invalid_composition_evidence",)})
    else:
        layout = replace(layout, rejected_composition_parts={"generic": ("invalid_composition_evidence",)})
    assert not same_region_recovery(layout, target, "generic", [raw, layout, target])


@pytest.mark.parametrize("defect", ["missing_character", "added_character", "changed_digit", "source_unboxed",
                                   "layout_unboxed", "observed_material", "observed_ratio", "other_part_material",
                                   "other_part_ratio", "missing_variant", "missing_region"])
def test_raw_peer_cannot_replace_a_literal_character_or_any_part_evidence(defect):
    raw, layout, target = _candidates()
    if defect == "missing_character":
        raw = replace(raw, text=raw.text.replace("중국", "중", 1))
    elif defect == "added_character":
        raw = replace(raw, text=raw.text + "魚")
    elif defect == "changed_digit":
        raw = replace(raw, text=raw.text.replace("5%", "75%", 1))
    elif defect == "source_unboxed":
        raw = replace(raw, text=raw.text + "\nOLEFIN")
    elif defect == "layout_unboxed":
        layout = replace(layout, text=layout.text + "\nUNKNOWN")
    elif defect == "observed_material":
        raw = replace(raw, observed_materials={"generic": ["polyester", "rayon"]})
    elif defect == "observed_ratio":
        raw = replace(raw, observed_ratios={"generic": [75, 21, 4]})
    elif defect == "other_part_material":
        raw = replace(raw, observed_materials=raw.observed_materials | {"lining": ["cotton"]})
    elif defect == "other_part_ratio":
        raw = replace(raw, observed_ratios=raw.observed_ratios | {"lining": [100]})
    elif defect == "missing_variant":
        layout = replace(layout, image_variant_key="")
    else:
        layout = replace(layout, image_region=())
    assert not same_region_recovery(layout, target, "generic", [raw, layout, target])


def test_evidence_order_can_change_only_when_each_part_multiset_is_preserved():
    raw, layout, target = _candidates()
    raw = replace(raw, observed_materials={"generic": list(reversed(raw.observed_materials["generic"]))},
                  observed_ratios={"generic": list(reversed(raw.observed_ratios["generic"]))})
    assert same_region_recovery(layout, target, "generic", [raw, layout, target])


@pytest.mark.parametrize("extra", ["OLEFIN", "FAUX", "UNKNOWN", "魚", "&", "UNREGISTERED",
                                  "%魚&", "10%", "-10%", "+10%", "드라이클리닝 호박섬유",
                                  "중성세제 미등록소재", "FOO BAR washing instructions",
                                  "魚 & washing instructions"])
def test_raw_layout_peer_cannot_delete_unknown_material_or_damaged_ratio(extra):
    raw, layout, target = _candidates(extra=extra)
    candidates = [raw, layout, target]
    assert not same_region_recovery(raw, target, "generic", candidates)
    assert not same_region_recovery(layout, target, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


def test_literal_raw_peer_cannot_hide_an_opaque_phrase_with_multiple_words():
    raw, layout, target = _candidates(extra="FOO BAR")
    candidates = [raw, layout, target]
    assert not same_region_recovery(raw, target, "generic", candidates)
    assert not same_region_recovery(layout, target, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("extra", ["FOO BAR washing instructions", "魚 & washing instructions",
                                  "드라이클리닝 호박섬유"])
def test_successful_reread_with_opaque_care_context_cannot_release_the_source_rejection(extra):
    raw, layout, target = _candidates()
    target = _build_payload_candidates(
        target.source, OcrPayload(target.text + "\n" + extra,
                                  layout_words=target.image_words + (_word(extra, 100, 223, 240, 16),)),
        image_key=target.image_key, image_variant_key=target.image_variant_key,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=target.image_region,
    )[0]
    assert target.parser_status == "success"
    candidates = [raw, layout, target]
    assert not same_region_recovery(raw, target, "generic", candidates)
    assert not same_region_recovery(layout, target, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"


@pytest.mark.parametrize("ratio", ["0.5", ".5", "5.0", "74", "95", "%魚&"])
def test_same_response_peer_does_not_invent_fractional_or_changed_integer_values(ratio):
    raw, layout, target = _candidates(ratio=ratio)
    candidates = [raw, layout, target]
    assert not same_region_recovery(layout, target, "generic", candidates)


@pytest.mark.parametrize("defect", ["missing_material", "missing_ratio", "outside_region", "wrong_ratio_row", "page"])
def test_literal_peer_still_requires_the_existing_complete_physical_reread_proof(defect):
    raw, layout, target = _candidates()
    if defect == "missing_material":
        target = replace(target, image_words=target.image_words[1:])
    elif defect == "missing_ratio":
        target = replace(target, image_words=target.image_words[:1] + target.image_words[2:])
    elif defect == "outside_region":
        target = replace(target, image_region=(80, 80, 330, 245))
    elif defect == "wrong_ratio_row":
        word = target.image_words[1]
        target = replace(target, image_words=target.image_words[:1] +
                         (replace(word, top=250, bottom=270,
                                  vertices=tuple((x, y + 145) for x, y in word.vertices)),) + target.image_words[2:])
    else:
        target = replace(target, image_words=tuple(replace(word, page=1) for word in target.image_words))
    assert not same_region_recovery(layout, target, "generic", [raw, layout, target])


def test_raw_and_layout_of_one_crop_are_not_two_independent_numeric_corrections():
    raw, layout, target = _candidates(ratio="74")
    duplicate = replace(target, layout_used=True, text="Polyester75%\nRayon21%\nSpan4%")
    candidates = [raw, layout, target, duplicate]
    assert not same_region_recovery(raw, target, "generic", candidates)
    assert not same_region_recovery(layout, target, "generic", candidates)
    assert _assess_candidates(candidates).status == "failed"
