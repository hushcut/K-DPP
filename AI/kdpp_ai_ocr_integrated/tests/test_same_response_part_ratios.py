"""Repeated percentages and split product numbers stay at their physical rows."""
from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _same_response_ratio_order_recovery
from apps.text.ocr_layout import OcrWord, spatial_text_from_words
from apps.text.ocr_text import OcrPayload, _build_payload_candidates, _assess_candidates


def word(text, x, y, width=70):
    return OcrWord(text, x, y, x + width, y + 18)


def readings():
    words = tuple(word(text, x, y, width) for text, x, y, width in [
        ("OUTER", 0, 0, 70), ("LEATHER", 85, 0, 100),
        ("CONTRAST", 0, 60, 85), ("POLYESTER", 95, 60, 105),
        ("100", 220, 60, 40), ("%", 270, 60, 15),
        ("LINING", 0, 120, 75), ("POLYESTER", 95, 120, 105),
        ("100", 220, 120, 40), ("%", 270, 120, 15),
        ("STYLE", 0, 200, 65), ("NO", 75, 200, 25), (":", 110, 200, 10),
        ("TEST", 140, 200, 50), ("-", 200, 200, 10), ("636", 220, 200, 40),
    ])
    raw = "OUTER LEATHER\nCONTRAST POLYESTER\nLINING POLYESTER\n100%\n100%\n-636\nSTYLE NO: TEST"
    cs = _build_payload_candidates("original", OcrPayload(raw,
        layout_text=spatial_text_from_words(list(words)), layout_words=words),
        image_key="same-photo", image_variant_key="same-input",
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 350, 240))
    assert len(cs) == 2
    return cs


def test_layout_pairs_repeated_percentages_and_keeps_unconfirmed_outer():
    raw, layout = readings()
    assert _same_response_ratio_order_recovery(raw, layout, "lining", [raw, layout])
    result = _assess_candidates([raw, layout])
    assert result.status == "success"
    assert result.best.selected_part == "lining"
    assert result.best.materials == {"polyester": 100}
    assert "outer" in result.rejected_composition_parts
    assert "lining" not in result.rejected_composition_parts
    assert "lining" not in result.unpaired_ratio_parts


@pytest.mark.parametrize("defect", [
    "different_photo", "different_input", "different_source", "missing_boxes", "changed_digit",
    "changed_word", "missing_region", "wrong_region", "reversed_layout", "extra_percentage",
    "unknown_lining", "unlabelled_product_code", "changed_material", "two_pages",
])
def test_ratio_reassignment_requires_identical_input_complete_rows_and_registered_context(defect):
    raw, layout = readings()
    if defect == "different_photo":
        layout = replace(layout, image_key="other-photo")
    elif defect == "different_input":
        layout = replace(layout, image_variant_key="other-input")
    elif defect == "different_source":
        layout = replace(layout, source="preprocessed")
    elif defect == "missing_boxes":
        layout = replace(layout, image_words=())
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("100", "90", 1))
    elif defect == "changed_word":
        layout = replace(layout, image_words=(replace(layout.image_words[0], text="BODY"),) + layout.image_words[1:])
    elif defect == "missing_region":
        layout = replace(layout, image_region=())
    elif defect == "wrong_region":
        raw = replace(raw, image_region=(0, 0, 349, 240))
    elif defect == "reversed_layout":
        layout = replace(layout, text="\n".join(reversed(layout.text.splitlines())))
    elif defect == "extra_percentage":
        raw = replace(raw, text=raw.text + "\n5%")
    elif defect == "unknown_lining":
        raw = replace(raw, rejected_composition_parts=raw.rejected_composition_parts | {"lining": ("unresolved_material_token",)})
    elif defect == "unlabelled_product_code":
        raw = replace(raw, text=raw.text.replace("STYLE NO:", "UNKNOWN:"))
        layout = replace(layout, text=layout.text.replace("STYLE NO :", "UNKNOWN :"))
    elif defect == "changed_material":
        raw = replace(raw, observed_materials=raw.observed_materials | {"lining": ["cotton"]})
    elif defect == "two_pages":
        raw = replace(raw, image_words=tuple(replace(w, page=1) if w.text == "100" else w for w in raw.image_words))
        layout = replace(layout, image_words=raw.image_words)
    assert not _same_response_ratio_order_recovery(raw, layout, "lining", [raw, layout])
