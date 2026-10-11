"""Literal primary fibers survive fully validated multilingual repeats."""

from dataclasses import replace
from io import BytesIO
import re

import pytest
from PIL import Image

from apps.text import ocr_text
from apps.text.material_extraction import find_material_key
from apps.text.ocr_candidates import agreed_original_composition
from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


LABEL = (
    "$123450\n100% COTTON-COTON-\nALGODÓN-ALGODÃO-\nPAMUK-COTONE-\n"
    "BAUMWOLLE-KATOEN-BA\nMBAKI-XNOПOK-BAWEŁNA\n-PAMUT-BAVLNA---\n"
    "$ 100%-KAPAS\nEXCLUSIVE OF DECORATION\nMACHINE WASH COLD"
)


def candidates(text=LABEL):
    words = []
    for row, line in enumerate(text.splitlines()):
        x, y = 20, 20 + row * 50
        for token in re.findall(r"[^\W\d_]+|\d+|[^\w\s]", line):
            width = max(12, len(token) * 12)
            words.append(OcrWord(token, x, y, x + width, y + 24,
                                 ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24))))
            x += width + 4
    # Layout order differs but retains every token and the same annotations.
    layout = "\n".join(reversed(re.findall(r"[^\W\d_]+|\d+|[^\w\s]", text)))
    raw, layout = _build_payload_candidates(
        "original", OcrPayload(text, layout, layout_words=tuple(words)),
        image_key="label-image", image_variant_key="original-input",
        image_region=(0, 0, 1800, 2000), image_transform=(1, 0, 0, 0, 1, 0),
    )
    return raw, layout


@pytest.mark.parametrize("glyph", ["XNOПOK", "XNONOK", "хлопок"])
@pytest.mark.parametrize("repeat", ["$ 100%-KAPAS", "100%-KAPAS", "100%-COTONE"])
def test_primary_literal_percentage_survives_same_fiber_repeated_declarations(glyph, repeat):
    text = LABEL.replace("XNOПOK", glyph).replace("$ 100%-KAPAS", repeat)
    raw, layout = candidates(text)
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["parse_evidence"]["observed_ratios"]["generic"] == [100.0]
    assert _assess_candidates([raw, layout]).status == "success"
    assert agreed_original_composition([raw, layout])
    assert raw.text == text
    assert raw.parser_confidence == ("medium" if glyph != "хлопок" or repeat.startswith("$") else "high")
    # A damaged translation never becomes a global standalone alias.
    if glyph != "хлопок":
        assert find_material_key(glyph) is None
        assert parse_label("100% " + glyph)["status"] == "failed"


@pytest.mark.parametrize("old,new", [
    ("XNOПOK", "CUSTOMFIBER"), ("XNOПOK", "UNKNOWN"), ("XNOПOK", "NYLON"),
    ("XNOПOK", "OLEFIN"), ("XNOПOK", "XNOPOK"), ("XNOПOK", "XNONOK2"),
    ("XNOПOK", "2"), ("XNOПOK", "0.5"), ("XNOПOK", "10%"),
    ("XNOПOK", "±"), ("XNOПOK", "-5"), ("XNOПOK", "PU"),
    ("100% COTTON", "99% COTTON"), ("100% COTTON", "-100% COTTON"),
    ("100% COTTON", "100 COTTON"), ("$ 100%-KAPAS", "$ 95%-KAPAS"),
    ("$ 100%-KAPAS", "$ 100%-NYLON"), ("$ 100%-KAPAS", "$ 100-KAPAS"),
    ("$ 100%-KAPAS", "$ 100%-KAPAS 2"), ("$ 100%-KAPAS", "$ -100%-KAPAS"),
    ("EXCLUSIVE OF DECORATION", "FOO"), ("BAWEŁNA", "XNONOK"),
    ("$123450", "FOO"), ("$123450", "UNKNOWN"),
    ("$123450", "$123450 COTTON"), ("$123450", "$123450%"),
    ("-PAMUT-BAVLNA---", "-PAMUT-BAVLNA--2-"),
    ("MACHINE WASH COLD", "NYLON 10%"),
])
def test_repeats_cannot_hide_unknown_materials_numbers_or_conflicting_evidence(old, new):
    result = parse_label(LABEL.replace(old, new))
    assert result["status"] == "failed", result


def test_short_translation_list_does_not_authorize_glyph_or_currency_cleanup():
    text = "100% COTTON-COTON-XNONOK\n$ 100%-KAPAS\nEXCLUSIVE OF DECORATION"
    assert parse_label(text)["status"] == "failed"


@pytest.mark.parametrize("amount", ["$123450", "€250.50", "£101", "₩150000"])
def test_standalone_amount_over_100_is_metadata_and_never_a_ratio(amount):
    assert parse_label(amount + "\nCOTTON 100%")["materials"] == {"cotton": 100}
    assert parse_label(amount + "\nCOTTON 70%")["status"] == "failed"


@pytest.mark.parametrize("amount", ["$30", "$100", "$-150", "$150%", "$150 OLEFIN", "$150 10%"])
def test_currency_does_not_mask_possible_percentages_signs_or_attached_materials(amount):
    assert parse_label(LABEL.replace("$123450", amount))["status"] == "failed"


@pytest.mark.parametrize("defect", [
    "other_image", "other_input", "other_source", "other_region", "missing_word",
    "extra_word", "duplicate_word", "missing_polygon", "different_page", "outside_region",
    "moved_primary", "moved_repeat", "moved_copy", "distant_copy", "rotated_copy",
    "incomplete_layout", "conflicting_layout",
])
def test_failed_layout_is_released_only_for_the_same_complete_physical_translation_list(defect):
    raw, layout = candidates()
    assert same_region_recovery(layout, raw, "generic", [raw, layout])
    if defect == "other_image":
        layout = replace(layout, image_key="other-image")
    elif defect == "other_input":
        layout = replace(layout, image_variant_key="other-input")
    elif defect == "other_source":
        layout = replace(layout, source="preprocessed")
    elif defect == "other_region":
        layout = replace(layout, image_region=(0, 0, 1500, 1500))
    elif defect == "incomplete_layout":
        layout = replace(layout, text=layout.text.replace("COTON", ""))
    elif defect == "conflicting_layout":
        layout = replace(layout, text=layout.text + "\nNYLON 10%")
    else:
        words = list(raw.image_words)
        token = "COTTON" if defect == "moved_primary" else "KAPAS" if defect == "moved_repeat" else "ALGODÓN"
        index = next(i for i, w in enumerate(words) if w.text == token)
        w = words[index]
        if defect == "missing_word":
            words.pop(index)
        elif defect == "extra_word":
            words.append(replace(w, text="NYLON"))
        elif defect == "duplicate_word":
            words.append(w)
        elif defect == "missing_polygon":
            words[index] = replace(w, vertices=())
        elif defect == "different_page":
            words[index] = replace(w, page=1)
        elif defect == "rotated_copy":
            words[index] = replace(w, vertices=(w.vertices[1], w.vertices[2], w.vertices[3], w.vertices[0]))
        else:
            dx, dy = (3000, 0) if defect == "outside_region" else (0, 500) if defect == "distant_copy" else (400, 0)
            words[index] = replace(w, left=w.left + dx, right=w.right + dx, top=w.top + dy, bottom=w.bottom + dy,
                                   vertices=tuple((x + dx, y + dy) for x, y in w.vertices))
        raw = replace(raw, image_words=tuple(words))
        layout = replace(layout, image_words=tuple(words))
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])
    assert not agreed_original_composition([raw, layout])


def test_verified_primary_list_keeps_medium_confidence_without_unneeded_ocr_retry(monkeypatch):
    raw, layout = candidates()
    payload = OcrPayload(raw.text, layout.text, layout_words=raw.image_words)
    calls = []

    def provider(_client, _content, **_kwargs):
        calls.append(True)
        return payload

    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_: object())
    monkeypatch.setattr(ocr_text, "_run_google_ocr", provider)
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda *_: pytest.fail("validated primary needs no retry"))
    content = BytesIO()
    Image.new("RGB", (1800, 2000), "white").save(content, format="JPEG")
    result = ocr_text.run_ocr_bytes(content.getvalue(), enable_material_region=True)
    assert len(calls) == result.metadata.candidate_count == result.metadata.attempt_count == 1
    assert result.metadata.confidence == "medium"
    assert result.text == LABEL
    assert not result.metadata.rejected_composition_parts
    assert parse_label(result.text)["materials"] == {"cotton": 100}


def test_primary_list_does_not_release_an_already_observed_unknown_other_response():
    raw, layout = candidates()
    bad, _ = candidates(LABEL.replace("XNOПOK", "OLEFIN"))
    bad = replace(bad, source="preprocessed", image_variant_key="other-input")
    assert _assess_candidates([raw, layout, bad]).status == "failed"
