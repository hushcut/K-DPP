"""Keep two literal composition rows separate from a trim-exclusion footer."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.ocr_corrections import _same_response_two_fiber_recovery, same_region_recovery
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label


def box(text, x, y, width, *, angle=0):
    theta = radians(angle)
    vertices = tuple((round(px * cos(theta) - py * sin(theta) + 700),
                      round(px * sin(theta) + py * cos(theta) + 700))
                     for px, py in ((x, y), (x + width, y), (x + width, y + 20), (x, y + 20)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def readings(*, angle=0, fibers=("COTTON", "POLYESTER"), ratios=(60, 40),
             prefix="EST.", footer="MACHINE WASH", fence=("EXCLUSIVE OF", "DECORATION"),
             name_first=False):
    first, second = fibers
    a, b = ratios
    if name_first:
        lines = (f"{first} {a}%", f"{second} {b}%")
    else:
        lines = (f"{a}% {first}", f"{b}% {second}")

    def row(name, ratio, y):
        if name_first:
            return (box(name, 20, y, 160, angle=angle),
                    box(str(ratio), 210, y, 50, angle=angle), box("%", 270, y, 32, angle=angle))
        return (box(str(ratio), 20, y, 50, angle=angle), box("%", 80, y, 32, angle=angle),
                box(name, 210, y, 160, angle=angle))

    words = row(first, a, 100) + row(second, b, 160)
    raw = list(lines) + list(fence)
    layout = [f"{a} %", f"{b} % {first}", second] + list(fence)
    for index, caption in enumerate(fence):
        words += (box(caption, 20, 240 + index * 60, 270, angle=angle),)
    if prefix:
        words += (box(prefix, 20, 20, 80, angle=angle),)
        raw.insert(0, prefix)
        layout.insert(0, prefix)
    if footer:
        words += (box(footer, 20, 430, 260, angle=angle),)
        raw.append(footer)
        layout.append(footer)
    # Exercise these two views directly: the provider may additionally build
    # a successful upright view and discard the bad layout for quarter turns.
    return tuple(replace(
        build_candidate("original", "\n".join(text), parse_candidate=parse_label, layout_used=used),
        image_key="one-label", image_variant_key="one-input", image_region=(0, 0, 2200, 2200),
        image_words=words,
    ) for text, used in ((raw, False), (layout, True)))


@pytest.mark.parametrize("angle", [-6, 0, 6, 90, -90])
@pytest.mark.parametrize("name_first", [False, True])
@pytest.mark.parametrize("fibers,ratios", [
    (("COTTON", "POLYESTER"), (60, 40)),
    (("NYLON", "SPANDEX"), (95, 5)),
    (("COTTON", "POLYESTER"), (62.5, 37.5)),
    (("COTTON", "POLYESTER"), (50, 50)),
])
def test_two_independent_rows_release_only_their_own_failed_layout(angle, name_first, fibers, ratios):
    raw, layout = readings(angle=angle, fibers=fibers, ratios=ratios, name_first=name_first)
    assert raw.parser_status == "success" and layout.parser_status == "failed"
    assert _same_response_two_fiber_recovery(layout, raw, "generic")
    assert same_region_recovery(layout, raw, "generic", [raw, layout])
    decision = _assess_candidates([raw, layout])
    assert decision.status == "success"
    assert decision.best.materials == dict(zip((x.lower() for x in fibers), ratios))
    assert decision.best.selected_part == "generic"


@pytest.mark.parametrize("prefix", ["", "EST.", "ESTD."])
@pytest.mark.parametrize("fence", [("EXCLUSIVE OF", "DECORATION"),
                                   ("EXCLUSIVE OF", "TRIM"), ("EXCLUSIVE OF TRIM",)])
def test_only_literal_exclusion_fences_and_establishment_captions_are_supported(prefix, fence):
    raw, layout = readings(prefix=prefix, fence=fence)
    assert _same_response_two_fiber_recovery(layout, raw, "generic")


@pytest.mark.parametrize("defect", [
    "image", "variant", "source", "region", "no_variant", "missing_word", "changed_digit",
    "correctable_typo", "changed_word", "extra_reason", "extra_part", "extra_observed_material",
    "extra_observed_ratio", "other_observed_part", "wrong_pair", "wrong_part",
])
def test_two_row_recovery_requires_literal_identity_and_preserves_rejected_evidence(defect):
    raw, layout = readings()
    if defect == "image":
        raw = replace(raw, image_key="other-label")
    elif defect == "variant":
        raw = replace(raw, image_variant_key="other-input")
    elif defect == "source":
        raw = replace(raw, source="preprocessed")
    elif defect == "region":
        raw = replace(raw, image_region=(0, 0, 2199, 2200))
    elif defect == "no_variant":
        raw = replace(raw, image_variant_key="")
    elif defect == "missing_word":
        raw = replace(raw, image_words=raw.image_words[:-1])
    elif defect == "changed_digit":
        layout = replace(layout, text=layout.text.replace("60", "50"))
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
    elif defect == "extra_observed_material":
        layout = replace(layout, observed_materials={"generic": ["cotton", "polyester", "nylon"]})
    elif defect == "extra_observed_ratio":
        layout = replace(layout, observed_ratios={"generic": [60, 40, 5]})
    elif defect == "other_observed_part":
        layout = replace(layout, observed_ratios=layout.observed_ratios | {"lining": [100]})
    elif defect == "wrong_pair":
        raw = replace(raw, parts={"generic": {"cotton": 40, "polyester": 60}})
    else:
        raw = replace(raw, selected_part="outer")
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


@pytest.mark.parametrize("index,defect", [
    (index, defect) for index in range(10)
    for defect in ("missing", "reverse", "other_page", "degenerate", "self_cross", "concave", "collinear")
    if defect != "reverse" or index < 8
])
def test_every_composition_and_fence_word_needs_its_own_valid_polygon(index, defect):
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[index]
    if defect == "missing":
        words[index] = replace(old, vertices=())
    elif defect == "reverse":
        a, b, c, d = old.vertices
        words[index] = replace(old, vertices=(b, a, d, c))
    elif defect == "other_page":
        words[index] = replace(old, page=1)
    elif defect == "degenerate":
        words[index] = replace(old, vertices=((old.left, old.top),) * 4)
    elif defect == "self_cross":
        a, b, c, d = old.vertices
        words[index] = replace(old, vertices=(a, b, d, c))
    elif defect == "concave":
        a, b, _c, d = old.vertices
        words[index] = replace(old, right=old.right, vertices=(a, b,
                               ((old.left + old.right) // 2, old.top + 1), d))
    else:
        a, b, _c, d = old.vertices
        words[index] = replace(old, right=old.right,
                               vertices=(a, b, ((a[0] + b[0]) // 2, a[1]), d))
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


def move(word, dx, dy):
    vertices = tuple((x + dx, y + dy) for x, y in word.vertices)
    return replace(word, left=word.left + dx, right=word.right + dx,
                   top=word.top + dy, bottom=word.bottom + dy, vertices=vertices)


@pytest.mark.parametrize("defect", ["swapped_ratios", "merged_rows", "ambiguous_rows", "same_row_margin", "reversed_rows",
                                   "footer_between", "footer_beside", "prefix_between",
                                   "duplicate_polygon", "folded_row", "opposed_slopes"])
def test_a_row_cannot_borrow_a_ratio_or_hide_context_inside_the_composition(defect):
    raw, layout = readings()
    words = list(raw.image_words)
    if defect == "swapped_ratios":
        words[0], words[3] = move(words[0], 0, 60), move(words[3], 0, -60)
    elif defect == "merged_rows":
        words[3:6] = [move(w, 0, -60) for w in words[3:6]]
    elif defect == "ambiguous_rows":
        words[3:6] = [move(w, 0, -50) for w in words[3:6]]
    elif defect == "same_row_margin":
        words[3:6] = [move(w, 0, -48) for w in words[3:6]]
    elif defect == "reversed_rows":
        words[:3], words[3:6] = [move(w, 0, 60) for w in words[:3]], [move(w, 0, -60) for w in words[3:6]]
    elif defect == "footer_between":
        words[-1] = move(words[-1], 0, -300)
    elif defect == "footer_beside":
        words[-1] = move(words[-1], 500, -330)
    elif defect == "prefix_between":
        words[-2] = move(words[-2], 0, 110)
    elif defect == "duplicate_polygon":
        words.append(words[0])
    elif defect == "folded_row":
        words[3:6] = [box(w.text, w.left - 700, w.top - 700, w.right - w.left, angle=8)
                      for w in words[3:6]]
    else:
        words[:3] = [box(w.text, w.left - 700, w.top - 700, w.right - w.left, angle=2)
                     for w in words[:3]]
        words[3:6] = [box(w.text, w.left - 700, w.top - 700, w.right - w.left, angle=-2)
                      for w in words[3:6]]
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


@pytest.mark.parametrize("prefix", ["FOO.", "NYL.", "MYSTERY", "COTTON", "SHELL", "EST. 1990"])
def test_arbitrary_prefixes_are_not_assumed_to_be_brand_metadata(prefix):
    raw, layout = readings(prefix=prefix)
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


@pytest.mark.parametrize("fence", [("EXCLUSIVE OF", "MYSTERY"), ("EXCLUSIVE OF", "COTTON"),
                                   ("TRIM",), ("EXCLUSIVE OF DECORATION ?",)])
def test_opaque_or_modified_exclusion_captions_are_not_fences(fence):
    raw, layout = readings(fence=fence)
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


@pytest.mark.parametrize("footer", ["UNKNOWN", "OLEFIN", "NYLON 5%", "5%", "SHELL COTTON 100%",
                                    "LINING COTTON 100%", "POLY/AMIDE", "FAUX LEATHER"])
def test_exclusion_cannot_hide_another_material_ratio_or_part(footer):
    raw, layout = readings(footer=footer)
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


def test_two_literal_rows_may_have_slightly_different_perspective_angles():
    raw, layout = readings()
    words = tuple(box(w.text, w.left - 700, w.top - 700, w.right - w.left,
                      angle=1 if index < 3 else 2)
                  for index, w in enumerate(raw.image_words))
    raw, layout = (replace(item, image_words=words) for item in (raw, layout))
    assert _same_response_two_fiber_recovery(layout, raw, "generic")


def test_padded_corners_may_overlap_when_the_complete_rows_and_pairing_are_unique():
    raw, layout = readings()
    words = list(raw.image_words)
    for index in range(3):
        word = words[index]
        a, b, (cx, cy), (dx, dy) = word.vertices
        words[index] = replace(word, bottom=word.bottom + 45,
                               vertices=(a, b, (cx, cy + 45), (dx, dy + 45)))
    assert words[0].bottom > words[3].top
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert _same_response_two_fiber_recovery(layout, raw, "generic")


def test_a_ratio_lost_only_from_layout_parsing_still_requires_complete_annotation_proof():
    raw, layout = readings()
    words = (raw.image_words[:6] + (box("EXCLUSIVE", 20, 240, 190), box("OF", 220, 240, 60))
             + raw.image_words[7:])
    raw = replace(raw, image_words=words)
    text = "EST.\n40 60 % COTTON\n%\nEXCLUSIVE POLYESTER\nOF\nDECORATION\nMACHINE WASH"
    layout = replace(build_candidate("original", text, parse_candidate=parse_label, layout_used=True),
                     image_key=raw.image_key, image_variant_key=raw.image_variant_key,
                     image_region=raw.image_region, image_words=words)
    assert layout.observed_ratios == {"generic": [40]}
    assert same_region_recovery(layout, raw, "generic", [raw, layout])
    layout = replace(layout, text=layout.text.replace("60", ""))
    assert not same_region_recovery(layout, raw, "generic", [raw, layout])


def test_a_thin_self_crossing_word_is_not_a_physical_material_row():
    raw, layout = readings()
    words = list(raw.image_words)
    old = words[2]
    x, y, right = old.left, old.top, old.right
    vertices = ((x, y), (right, y), (right, y - 1), (x, y + 1))
    words[2] = replace(old, top=y - 1, bottom=y + 1, vertices=vertices)
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not _same_response_two_fiber_recovery(layout, raw, "generic")


@pytest.mark.parametrize("index", [8, 9])
def test_noncomposition_captions_can_have_a_different_reading_direction(index):
    raw, layout = readings()
    words = list(raw.image_words)
    a, b, c, d = words[index].vertices
    words[index] = replace(words[index], vertices=(b, a, d, c))
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert _same_response_two_fiber_recovery(layout, raw, "generic")
