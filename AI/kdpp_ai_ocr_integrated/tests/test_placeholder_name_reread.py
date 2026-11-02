"""A material placeholder needs its own observed row, never another block's success."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _physical_row, _annotation_tokens, _row_words
from apps.text.ocr_layout import OcrWord, spatial_text_from_words
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


NAMES = ("ポリエステル", "綿", "ポリウレタン")
RATIOS = (40, 37, 23)


def _word(text, x, y, width, *, skew=0):
    points = ((x, y), (x + width, y + skew), (x + width, y + 24), (x, y + 24))
    return OcrWord(text, x, y, x + width, y + 24, points)


def _reading(*, source="original", placeholder="**", names=NAMES, quantised=False):
    labels = (names[0], placeholder, names[2]) if source == "original" else names
    words = []
    for index, (name, ratio) in enumerate(zip(labels, RATIOS, strict=True)):
        y = 100 + index * 60
        words.extend((_word(str(ratio), 100, y, 28),
                      _word("%", 135, y, 11, skew=int(quantised and index == 1)),
                      _word(name, 180, y, max(28, len(name) * 18))))
    text = "\n".join(f"{ratio}% {name}" for ratio, name in zip(RATIOS, labels, strict=True))
    return _build_payload_candidates(
        source, OcrPayload(text, layout_text=spatial_text_from_words(words), layout_words=tuple(words)),
        image_key="one-photo", image_variant_key=source + "-input",
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(60, 60, 600, 280),
    )


def _pair(**kwargs):
    original = _reading(**{key: value for key, value in kwargs.items() if key != "quantised"})
    crop = _reading(source="material_crop", **{key: value for key, value in kwargs.items() if key != "placeholder"})
    assert all(candidate.parser_status == "failed" for candidate in original)
    assert all(candidate.parser_status == "success" for candidate in crop)
    return original, crop


@pytest.mark.parametrize("names", [NAMES, ("聚酯纤维", "棉", "氨纶"), ("폴리에스터", "면", "폴리우레탄")])
@pytest.mark.parametrize("placeholder", ["*", "**", "?", "???"])
@pytest.mark.parametrize("quantised", [False, True])
def test_one_complete_overlapping_reread_replaces_only_the_boxed_material_cell(names, placeholder, quantised):
    original, crop = _pair(names=names, placeholder=placeholder, quantised=quantised)
    for candidates in (original + crop, crop + original):
        decision = _assess_candidates(candidates)
        assert decision.status == "success"
        assert decision.best.materials == crop[0].materials
        assert decision.rejected_composition_parts == {}
        assert decision.unpaired_ratio_parts == ()


def test_small_percent_vertex_quantisation_is_checked_only_inside_the_complete_reread_proof():
    original, crop = _pair(quantised=True)
    layout = next(candidate for candidate in crop if candidate.layout_used)
    line = layout.text.splitlines()[1]
    words = _row_words(line, layout.image_words, tokenise=_annotation_tokens)
    assert not _physical_row(line, words, tokenise=_annotation_tokens)
    assert _physical_row(line, words, allow_quantisation=True, tokenise=_annotation_tokens)
    assert _assess_candidates(original + crop).status == "success"


@pytest.mark.parametrize("defect", [
    "different_photo", "same_input", "same_source", "different_page", "different_part",
    "changed_ratio", "changed_known_fiber", "two_placeholders", "unknown_fiber",
    "unboxed_text", "missing_percent", "reused_percent", "missing_vertices",
    "moved_placeholder", "moved_reread_name", "cropped_out_known_row", "joined_unknown_cell",
    "opaque_context", "material_warning", "larger_percent_skew",
])
def test_reread_cannot_hide_changed_incomplete_ambiguous_or_unlocated_evidence(defect):
    original, crop = _pair()
    if defect == "different_photo":
        crop = [replace(c, image_key="another-photo") for c in crop]
    elif defect == "same_input":
        crop = [replace(c, image_variant_key=original[0].image_variant_key) for c in crop]
    elif defect == "same_source":
        crop = [replace(c, source=original[0].source) for c in crop]
    elif defect == "different_page":
        crop = [replace(c, image_words=tuple(replace(w, page=1) for w in c.image_words)) for c in crop]
    elif defect == "different_part":
        crop = [replace(c, parts={"outer": c.materials}, selected_part="outer") for c in crop]
    elif defect == "changed_ratio":
        original = [replace(c, text=c.text.replace("37", "38"),
                            image_words=tuple(replace(w, text="38") if w.text == "37" else w for w in c.image_words))
                    for c in original]
    elif defect == "changed_known_fiber":
        crop = _reading(source="material_crop", names=("ナイロン", "綿", "ポリウレタン"))
    elif defect == "two_placeholders":
        original = _reading(names=("?", "綿", "ポリウレタン"))
    elif defect == "unknown_fiber":
        original = _reading(placeholder="OLEFIN")
    elif defect == "unboxed_text":
        original = [replace(c, text=c.text + "\nUNKNOWN") for c in original]
    elif defect == "missing_percent":
        crop = [replace(c, image_words=tuple(w for w in c.image_words if not (w.text == "%" and w.top == 160)))
                for c in crop]
    elif defect == "reused_percent":
        original = [replace(c, image_words=tuple(
            next(w for w in c.image_words if w.text == "%" and w.top == 100)
            if w.text == "%" and w.top == 160 else w for w in c.image_words)) for c in original]
    elif defect == "missing_vertices":
        original = [replace(c, image_words=tuple(replace(w, vertices=()) if w.text == "**" else w
                                                 for w in c.image_words)) for c in original]
    elif defect in {"moved_placeholder", "moved_reread_name"}:
        selected = original if defect == "moved_placeholder" else crop
        name = "**" if defect == "moved_placeholder" else "綿"
        shifted = [replace(c, image_words=tuple(_word(name, 400, 160, 28) if w.text == name else w
                                                for w in c.image_words)) for c in selected]
        if defect == "moved_placeholder":
            original = shifted
        else:
            crop = shifted
    elif defect == "cropped_out_known_row":
        crop = [replace(c, image_region=(60, 150, 600, 280)) for c in crop]
    elif defect == "joined_unknown_cell":
        original = [replace(c, image_words=tuple(w for w in c.image_words if w.top != 160)
                             + (_word("37%**", 100, 160, 108),)) for c in original]
    elif defect in {"opaque_context", "material_warning"}:
        text = "OPAQUE" if defect == "opaque_context" else "未知繊維"
        original = [replace(c, text=c.text + "\n" + text,
                            image_words=c.image_words + (_word(text, 180, 250, 90),)) for c in original]
    else:
        crop = [replace(c, image_words=tuple(_word("%", 135, 160, 11, skew=2)
                                             if w.text == "%" and w.top == 160 else w
                                             for w in c.image_words)) for c in crop]
    assert _assess_candidates(original + crop).status == "failed"


@pytest.mark.parametrize("defect", ["image", "variant", "region", "words", "observed_ratios", "paired_materials"])
def test_raw_candidate_can_use_only_its_exact_layout_peer(defect):
    original, crop = _pair()
    raw, layout = original
    if defect == "image":
        layout = replace(layout, image_key="other-photo")
    elif defect == "variant":
        layout = replace(layout, image_variant_key="other-input")
    elif defect == "region":
        layout = replace(layout, image_region=(60, 60, 601, 280))
    elif defect == "words":
        layout = replace(layout, image_words=tuple(replace(w, left=w.left + 1) for w in layout.image_words))
    elif defect == "observed_ratios":
        layout = replace(layout, observed_ratios={"generic": [40, 38, 23]})
    else:
        layout = replace(layout, paired_material_ratios={"generic": [("polyester", 37), ("polyurethane", 23)]})
    from apps.text.ocr_corrections import same_region_recovery

    reread = next(c for c in crop if c.layout_used)
    assert not same_region_recovery(raw, reread, "generic", [raw, layout] + crop)
