"""A same-response main recovery never clears rib or lining evidence."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.main_material_recovery import recover_main_material_layout
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_corrections import _literal_name_tokens, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label


def box(text, y, *, width=800, angle=0):
    theta = radians(angle)
    points = tuple((round(x * cos(theta) - yy * sin(theta) + 1500),
                    round(x * sin(theta) + yy * cos(theta) + 1500))
                   for x, yy in ((0, y), (width, y), (width, y + 20), (0, y + 20)))
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), points)


def readings(*, angle=0, property_text="(100% RECYCLED)", extra="OSME"):
    first = f"100% POLYESTER {property_text}"
    rows = [
        ("GB: MAIN MATERIAL:", 100), (extra, 20), (first, 150),
        ("RIB PART: 95% POLYESTER / 5% ELASTANE", 240),
        ("F: MATIERE PRINCIPALE:", 340), ("100% POLYESTER (100% RECYCLE)", 390),
        ("EMPIECEMENT EN BORD COTE:", 470), ("95% POLYESTER / MD5% ELASTHANE", 510),
        ("CN:主料:100%聚酯纤维(再生)", 600), ("里料:100%聚酯纤维", 690),
    ]
    text = "\n".join(line for line, _ in rows)
    words = tuple(box(line, y, angle=angle) for line, y in rows)
    raw = replace(build_candidate("original", text, parse_candidate=parse_label),
                  image_key="one-image", image_variant_key="one-input",
                  image_region=(0, 0, 4000, 4000), image_words=words)
    layout = replace(raw, layout_used=True, parser_status="failed", parts={}, selected_part="",
                     rejected_composition_parts={"outer": ("unpaired_material_rows", "unresolved_material_token"),
                                                 "rib": ("invalid_composition_evidence",)},
                     observed_ratios={**raw.observed_ratios, "outer": [100, 100, 100, 100]})
    return raw, layout


def recover(raw, layout):
    return recover_main_material_layout(layout, raw, "outer", tokenise=_literal_name_tokens)


@pytest.mark.parametrize("angle", [0, -6, 6, 90, -90])
def test_all_three_printed_main_blocks_prove_only_the_outer_rejection(angle):
    raw, layout = readings(angle=angle)
    assert raw.parser_status == "success" and raw.parts["outer"] == {"polyester": 100}
    assert recover(raw, layout)
    assert "rib" in layout.rejected_composition_parts
    assert "rib" in raw.rejected_composition_parts


def test_the_final_decision_releases_only_outer_and_retains_the_lower_part_rejection():
    raw, layout = readings()
    assert same_region_recovery(layout, raw, "outer", [raw, layout])
    assert not same_region_recovery(layout, raw, "rib", [raw, layout])
    result = _assess_candidates([raw, layout])
    assert result.status == "success"
    assert result.best.selected_part == "outer"
    assert result.best.materials == {"polyester": 100}
    assert "outer" not in result.rejected_composition_parts
    assert "rib" in result.rejected_composition_parts


@pytest.mark.parametrize("defect", ["image", "variant", "source", "region", "missing_variant",
                                   "extra_ratio", "extra_material", "invalid_ratio", "outer_conflict",
                                   "second_outer", "different_part", "changed_character"])
def test_provenance_and_independent_main_errors_are_preserved(defect):
    raw, layout = readings()
    if defect == "image":
        raw = replace(raw, image_key="other")
    elif defect == "variant":
        raw = replace(raw, image_variant_key="other")
    elif defect == "source":
        raw = replace(raw, source="other")
    elif defect == "region":
        raw = replace(raw, image_region=(0, 0, 3999, 4000))
    elif defect == "missing_variant":
        layout = replace(layout, image_variant_key="")
    elif defect == "extra_ratio":
        layout = replace(layout, observed_ratios={"outer": [100, 100, 100, 5]})
    elif defect == "extra_material":
        layout = replace(layout, observed_materials={**layout.observed_materials,
                                                     "outer": ["polyester", "polyester", "cotton"]})
    elif defect == "invalid_ratio":
        layout = replace(layout, rejected_composition_parts={"outer": ("invalid_ratio",)})
    elif defect == "outer_conflict":
        raw = replace(raw, conflicting_parts=("outer",))
    elif defect == "second_outer":
        raw = replace(raw, observed_materials={**raw.observed_materials, "outer_2": ["cotton"]})
    elif defect == "different_part":
        raw = replace(raw, selected_part="lining")
    else:
        layout = replace(layout, text=layout.text.replace("POLYESTER", "P0LYESTER", 1))
    assert not recover(raw, layout)


@pytest.mark.parametrize("property_text", ["(100% COTTON)", "(100% NOT RECYCLED)",
                                          "(1000% RECYCLED)", "(100% RECYCLED", "100%"])
def test_other_compositions_and_broken_properties_are_not_recycled_notes(property_text):
    raw, layout = readings(property_text=property_text)
    assert not recover(raw, layout)


@pytest.mark.parametrize("index", [0, 2, 3, 4, 5, 6, 8])
@pytest.mark.parametrize("defect", ["missing_polygon", "reverse", "other_page", "wrong_row"])
def test_every_required_heading_boundary_and_body_needs_physical_proof(index, defect):
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[index]
    if defect == "missing_polygon":
        words[index] = replace(old, vertices=())
    elif defect == "reverse":
        a, b, c, d = old.vertices
        words[index] = replace(old, vertices=(b, a, d, c))
    elif defect == "other_page":
        words[index] = replace(old, page=1)
    else:
        points = tuple((x, y + 300) for x, y in old.vertices)
        words[index] = replace(old, top=old.top + 300, bottom=old.bottom + 300, vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not recover(raw, layout)


def test_opaque_caption_cannot_be_hidden_inside_main_material_by_paragraph_order():
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[1]
    points = tuple((x, y + 120) for x, y in old.vertices)
    words[1] = replace(old, top=old.top + 120, bottom=old.bottom + 120, vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not recover(raw, layout)


@pytest.mark.parametrize("dx", [0, 1000])
def test_lower_part_annotation_cannot_be_hidden_beside_the_chinese_main_row(dx):
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[7]
    points = tuple((x + dx, y + 90) for x, y in old.vertices)
    words[7] = replace(old, left=old.left + dx, right=old.right + dx,
                       top=old.top + 90, bottom=old.bottom + 90, vertices=points)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not recover(raw, layout)


@pytest.mark.parametrize("extra", ["UNKNOWN", "FAUX", "OLEFIN", "COTTON", "10%", "未知纤维", "未知繊維"])
def test_unregistered_materials_and_percentages_are_not_brand_captions(extra):
    raw, layout = readings(extra=extra)
    assert not recover(raw, layout)
