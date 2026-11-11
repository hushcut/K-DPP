"""A written, independently located care band cannot hide composition evidence."""

from dataclasses import replace

import pytest

from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label
from apps.text.written_care_band_recovery import recover_written_care_band


def box(text, x, y, width, height=30):
    return OcrWord(
        text,
        x,
        y,
        x + width,
        y + height,
        ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        0,
    )


def readings(number="3", fiber="COTTON"):
    result = []
    for source, layout, joined in [("original", False, True), ("preprocessed", True, False)]:
        wash = "MACHINE WASHCOLD" if joined else "MACHINE WASH COLD"
        lines = [f"100% {fiber}", wash, "TUMBLE DRYLOW"]
        words = (
            box("100%", 100, 100, 80),
            box(fiber, 210, 100, 180),
            box(wash, 100, 220, 400),
            box("TUMBLE DRYLOW", 100, 300, 400),
        )
        if source == "original":
            lines.append(number)
            words += (box(number, 400, 400, 50, 70),)
        lines.append("RN·12345 CA·67890")
        words += (box("RN·12345 CA·67890", 100, 550, 500),)
        result.append(
            replace(
                build_candidate(
                    source, "\n".join(lines), parse_candidate=parse_label, layout_used=layout
                ),
                image_key="same-photo",
                image_variant_key=source,
                image_region=(0, 0, 1000, 1000),
                image_words=words,
            )
        )
    return result


@pytest.mark.parametrize("number", ["3", "7", "30"])
@pytest.mark.parametrize("fiber", ["COTTON", "POLYESTER"])
def test_complete_material_and_both_written_care_rows_bound_a_separate_number(number, fiber):
    raw, peer = readings(number, fiber)
    assert recover_written_care_band(raw, peer, "generic")
    result = _assess_candidates([raw, peer])
    assert result.status == "success"
    assert result.best.materials == {fiber.lower(): 100}
    assert result.best.selected_part == "generic"
    assert not recover_written_care_band(raw, peer, "outer")


def test_a_complete_generic_reread_cannot_hide_an_unconfirmed_outer():
    raw, peer = readings()
    peer = replace(peer, unconfirmed_outer_parts=("outer",))
    assert not recover_written_care_band(raw, peer, "generic")


@pytest.mark.parametrize(
    "extra",
    ["-20", "0", "0/0", "8%", "UNKNOWN", "OLEFIN 20%", "NYON 20%", "POLYESTER", "LINING", "7"],
)
def test_other_invalid_values_unknown_materials_or_parts_are_not_erased(extra):
    raw, peer = readings()
    raw = replace(
        build_candidate("original", raw.text + "\n" + extra, parse_candidate=parse_label),
        image_key=raw.image_key,
        image_variant_key=raw.image_variant_key,
        image_region=raw.image_region,
        image_words=raw.image_words + (box(extra, 650, 420, 100),),
    )
    assert not recover_written_care_band(raw, peer, "generic")


@pytest.mark.parametrize(
    "defect",
    [
        "image",
        "same_variant",
        "crop",
        "not_layout",
        "geometry",
        "same_page",
        "missing_wash",
        "missing_dry",
        "missing_registration",
        "changed_registration",
        "shifted_core",
        "number_before_dry",
        "number_below_footer",
        "unknown_band_word",
        "number_percent",
        "ratio_mismatch",
        "extra_warning",
        "second_percentage",
    ],
)
def test_both_literal_fences_location_and_provenance_are_required(defect):
    raw, peer = readings()
    if defect == "image":
        peer = replace(peer, image_key="other")
    elif defect == "same_variant":
        peer = replace(peer, image_variant_key=raw.image_variant_key)
    elif defect == "crop":
        peer = replace(peer, source="material_crop")
    elif defect == "not_layout":
        peer = replace(peer, layout_used=False)
    elif defect in {
        "geometry",
        "same_page",
        "shifted_core",
        "number_before_dry",
        "number_below_footer",
    }:
        words = list(raw.image_words)
        if defect == "geometry":
            words[0] = replace(words[0], vertices=())
        elif defect == "same_page":
            words[-2] = replace(words[-2], page=1)
        elif defect == "shifted_core":
            words[0] = box("100%", 100, 40, 80)
        elif defect == "number_before_dry":
            words[-2] = box("3", 400, 270, 50, 20)
        else:
            words[-2] = box("3", 400, 650, 50, 70)
        raw = replace(raw, image_words=tuple(words))
    elif defect in {"missing_wash", "missing_dry", "missing_registration", "changed_registration"}:
        old, new = {
            "missing_wash": ("MACHINE WASHCOLD", "UNKNOWN"),
            "missing_dry": ("TUMBLE DRYLOW", "UNKNOWN"),
            "missing_registration": ("RN·12345 CA·67890", "UNKNOWN"),
            "changed_registration": ("RN·12345 CA·67890", "RN·12346 CA·67890"),
        }[defect]
        raw = replace(
            raw,
            text=raw.text.replace(old, new),
            image_words=tuple(
                replace(w, text=new) if w.text == old else w for w in raw.image_words
            ),
        )
    elif defect == "unknown_band_word":
        raw = replace(
            raw,
            text=raw.text + "\nNYON",
            image_words=raw.image_words + (box("NYON", 650, 420, 100),),
        )
    elif defect == "number_percent":
        raw = replace(
            raw,
            text=raw.text.replace("\n3\n", "\n3%\n"),
            image_words=tuple(
                replace(w, text="3%") if w.text == "3" else w for w in raw.image_words
            ),
        )
    elif defect == "ratio_mismatch":
        raw = replace(raw, observed_ratios={"generic": [90, 3]})
    elif defect == "extra_warning":
        raw = replace(
            raw, parser_warnings=raw.parser_warnings + ("generic:unresolved_material_token",)
        )
    else:
        raw = replace(
            raw,
            text=raw.text + "\n100%",
            image_words=raw.image_words + (box("100%", 650, 700, 100),),
        )
    assert not recover_written_care_band(raw, peer, "generic")
