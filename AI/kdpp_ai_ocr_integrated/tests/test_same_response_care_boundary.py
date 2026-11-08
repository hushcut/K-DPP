"""Prove a complete first fiber row separately from the care footer."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def box(text, x, y, width, *, angle=0):
    theta = radians(angle)
    vertices = tuple((round(px * cos(theta) - py * sin(theta) + 700),
                      round(px * sin(theta) + py * cos(theta) + 700))
                     for px, py in ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def readings(*, angle=0, material="COTTON", footer="STYLE ZX1234", care="MACHINE WASH", prefix=""):
    words = (
        box("100", 20, 20, 50, angle=angle), box("%", 75, 20, 20, angle=angle),
        box(material, 180, 20, 140, angle=angle),
        box("MACHINE", 20, 100, 120, angle=angle), box("WASH", 150, 100, 80, angle=angle),
    )
    raw = f"100% {material}\n{care}"
    layout = f"100 %\nMACHINE {material}\nWASH"
    if care != "MACHINE WASH":
        words = words[:3] + (box(care, 20, 100, 220, angle=angle),)
        layout = f"100 %\n{care} {material}"
    if footer:
        raw += "\n" + footer
        layout += "\n" + footer
        words += (box(footer, 20, 180, 240, angle=angle),)
    if prefix:
        raw = prefix + "\n" + raw
        layout = prefix + "\n" + layout
        words += (box(prefix, 20, -60, 180, angle=angle),)
    candidates = _build_payload_candidates(
        "original", OcrPayload(raw, layout_text=layout, layout_words=words),
        image_key="one-label", image_variant_key="one-input", image_region=(0, 0, 2000, 2000),
        image_transform=(1, 0, 0, 0, 1, 0),
    )
    # Quarter-turn inputs may also have an upright geometry candidate. This
    # test isolates the raw view and the faulty provider layout view.
    return candidates[0], candidates[1]


@pytest.mark.parametrize("angle", [-6, 0, 6, 90, -90])
@pytest.mark.parametrize("material", ["COTTON", "POLYESTER", "NYLON"])
def test_literal_first_composition_is_not_vetoed_by_its_shuffled_care_footer(angle, material):
    raw, layout = readings(angle=angle, material=material)
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    assert same_region_recovery(layout, raw, "generic", [raw, layout])
    decision = _assess_candidates([raw, layout])
    assert decision.status == "success"
    assert decision.best.materials == {material.lower(): 100}
    assert decision.best.selected_part == "generic"
    assert "ZX1234" in raw.text and "ZX1234" in layout.text


@pytest.mark.parametrize("defect", [
    "image", "variant", "source", "region", "missing_variant", "missing_words", "changed_digit",
    "changed_letter", "correctable_typo", "changed_word", "extra_reason", "extra_part",
    "other_observed_material", "other_observed_ratio",
])
def test_care_boundary_needs_the_same_literal_response_and_evidence(defect):
    raw, layout = readings()
    if defect == "image":
        raw = replace(raw, image_key="another-label")
    elif defect == "variant":
        raw = replace(raw, image_variant_key="another-input")
    elif defect == "source":
        raw = replace(raw, source="preprocessed")
    elif defect == "region":
        raw = replace(raw, image_region=(0, 0, 1999, 2000))
    elif defect == "missing_variant":
        raw = replace(raw, image_variant_key="")
    elif defect == "missing_words":
        raw = replace(raw, image_words=raw.image_words[:-1])
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("100", "10"))
    elif defect == "changed_letter":
        layout = replace(layout, text=layout.text.replace("COTTON", "COTON"))
    elif defect == "correctable_typo":
        layout = replace(layout, text=layout.text.replace("COTTON", "C0TTON"))
    elif defect == "changed_word":
        words = tuple(replace(w, text="C0TTON") if w.text == "COTTON" else w for w in raw.image_words)
        raw, layout = (replace(item, image_words=words) for item in (raw, layout))
    elif defect == "extra_reason":
        layout = replace(layout, rejected_composition_parts={"generic": ("unresolved_material_token",)})
    elif defect == "extra_part":
        layout = replace(layout, rejected_composition_parts=layout.rejected_composition_parts | {
            "outer": ("unpaired_material_rows",),
        })
    elif defect == "other_observed_material":
        layout = replace(layout, observed_materials={"generic": ["nylon"]})
    else:
        layout = replace(layout, observed_ratios={"generic": [10]})
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize("defect", ["missing", "reverse", "other_row", "other_page", "degenerate"])
def test_composition_and_care_require_complete_separate_polygons(index, defect):
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[index]
    if defect == "missing":
        words[index] = replace(old, vertices=())
    elif defect == "reverse":
        a, b, c, d = old.vertices
        words[index] = replace(old, vertices=(b, a, d, c))
    elif defect == "other_row":
        shift = 100 if index < 3 else -80
        points = tuple((x, y + shift) for x, y in old.vertices)
        words[index] = replace(old, top=old.top + shift, bottom=old.bottom + shift, vertices=points)
    elif defect == "other_page":
        words[index] = replace(old, page=1)
    else:
        words[index] = replace(old, vertices=((old.left, old.top),) * 4)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])


@pytest.mark.parametrize("care", ["WASHING MAYBE", "MACHINE WASH ?", "MACHINE WASH 30%", "UNKNOWN"])
def test_an_opaque_or_numeric_caption_does_not_supply_a_care_boundary(care):
    raw, layout = readings(care=care)
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])


@pytest.mark.parametrize("footer", ["UNKNOWN", "OLEFIN", "NYLON 10%", "10%", "LINING COTTON 100%"])
def test_care_boundary_preserves_extra_materials_ratios_and_parts(footer):
    raw, layout = readings(footer=footer)
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])
    decision = _assess_candidates([raw, layout])
    if footer.startswith("LINING"):
        # A separately complete lining is existing valid evidence, not a
        # reason to relax this generic-only exception or erase the part.
        assert decision.best.parts["lining"] == {"cotton": 100}
    else:
        assert decision.status == "failed"


@pytest.mark.parametrize("prefix", ["BRAND", "COMPOSITION", "OUTER", "100% COTTON"])
def test_only_the_first_complete_row_is_eligible(prefix):
    raw, layout = readings(prefix=prefix)
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])


def test_a_footer_moved_into_the_composition_band_is_not_context():
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[-1]
    points = tuple((x + 500, y - 160) for x, y in old.vertices)
    words[-1] = replace(old, left=old.left + 500, right=old.right + 500,
                        top=old.top - 160, bottom=old.bottom - 160, vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])
