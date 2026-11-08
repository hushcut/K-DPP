"""Every repeated outer row needs unchanged, same-place physical evidence."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.multilingual_layout_recovery import recover_multilingual_outer_layout
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_corrections import _literal_name_tokens, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label


ROWS = (("SHELL", "COTTON", "POLYESTER"), ("面料", "棉", "聚酯纤维"),
        ("面料", "棉", "聚酯纖維"), ("겉감", "면", "폴리에스터"))


def box(text, x, y, width, angle=0, local_angle=0):
    points = ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24))
    local = radians(local_angle)
    cx, cy = x + width / 2, y + 12
    points = tuple((cx + (px - cx) * cos(local) - (py - cy) * sin(local),
                    cy + (px - cx) * sin(local) + (py - cy) * cos(local)) for px, py in points)
    theta = radians(angle)
    vertices = tuple((round(px * cos(theta) - py * sin(theta) + 1000),
                      round(px * sin(theta) + py * cos(theta) + 1000)) for px, py in points)
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def readings(angle=0, ratios=(55, 45), curved=True, prefix=True, footer=True):
    a, b = ratios
    lines, source_words, target_words = [], [], []
    for row_index, (heading, first, second) in enumerate(ROWS):
        y = 120 + row_index * 110
        lines.append(f"{heading}: {a}% {first}, {b}% {second}")
        cells = ((heading, 20, 110), (":", 135, 24), (str(a), 170, 50), ("%", 230, 40),
                 (first, 300, 140), (",", 450, 24), (str(b), 500, 50), ("%", 560, 40),
                 (second, 640, 180))
        for cell_index, (text, x, width) in enumerate(cells):
            source_words.append(box(text, x, y, width, angle, 8 if curved and row_index == 0 and cell_index == 8 else 0))
            target_words.append(box(text, x, y, width, angle))
    layout = [ROWS[0][2], f"{b}%", ROWS[0][1] + ",", f"SHELL: {a}%"] + lines[1:]
    if prefix:
        before = ("STYLE NO:", "SKU1234-Z9") if prefix is True else prefix
        lines[:0] = before
        layout[:0] = lines[:2]
        captions = (box(before[0], 20, 0, 180, angle), box(before[1], 250, 0, 240, angle))
        source_words.extend(captions)
        target_words.extend(captions)
    if footer:
        captions = ["384", "단추가 탈락되면 삼킬 수 있으므로 주의 하십시오."] if footer is True else footer
        lines.extend(captions)
        layout.extend(captions)
        for i, text in enumerate(captions):
            word = box(text, 20, 650 + i * 60, 80 if i == 0 else 800, angle)
            source_words.append(word)
            target_words.append(word)

    def candidate(text, source, words, layout_used=False):
        return replace(build_candidate(source, "\n".join(text), parse_candidate=parse_label,
                                       layout_used=layout_used), image_key="same-label",
                       image_variant_key=source, image_region=(0, 0, 2800, 2800), image_words=tuple(words))

    return [candidate(lines, "original", source_words), candidate(layout, "original", source_words, True),
            candidate(lines, "material_crop_rotated", target_words)]


def recovery(items):
    raw, layout, *_ = items
    return recover_multilingual_outer_layout(layout, raw, "generic", items, tokenise=_literal_name_tokens)


@pytest.mark.parametrize("angle", [0, 6, -6, 90, -90])
@pytest.mark.parametrize("ratios", [(55, 45), (60, 40), (62.5, 37.5)])
@pytest.mark.parametrize("curved", [False, True])
def test_repeated_outer_declarations_require_a_separate_same_place_physical_reread(angle, ratios, curved):
    items = readings(angle, ratios, curved)
    assert items[0].parser_status == "success" and items[1].parser_status == "failed"
    assert recovery(items)
    assert same_region_recovery(items[1], items[0], "generic", items)
    decision = _assess_candidates(items)
    assert decision.status == "success"
    assert decision.best.materials == dict(zip(("cotton", "polyester"), ratios))
    assert decision.best.selected_part == "outer"


@pytest.mark.parametrize("prefix,footer", [(False, False), (True, False), (False, True)])
def test_a_crop_may_omit_metadata_but_must_keep_all_declaration_rows(prefix, footer):
    items = readings(prefix=prefix, footer=footer)
    assert recovery(items)


def test_two_views_of_one_response_are_not_an_independent_reread():
    items = readings()
    assert not recovery(items[:2])


@pytest.mark.parametrize("defect", ["image", "variant", "source", "same_layout", "missing_row",
                                   "changed_ratio", "changed_letter", "correctable_typo", "part",
                                   "missing_word", "extra_word", "bad_physical_row", "other_page"])
def test_an_incomplete_different_or_unverified_reread_cannot_supply_the_proof(defect):
    raw, layout, target = readings()
    if defect == "image":
        target = replace(target, image_key="other-label")
    elif defect == "variant":
        target = replace(target, image_variant_key=raw.image_variant_key)
    elif defect == "source":
        target = replace(target, source=raw.source)
    elif defect == "same_layout":
        target = replace(target, layout_used=True)
    elif defect == "missing_row":
        target = replace(target, text="\n".join(line for line in target.text.splitlines() if not line.startswith("겉감")))
    elif defect == "changed_ratio":
        target = replace(target, text=target.text.replace("55", "65").replace("45", "35"))
    elif defect == "changed_letter":
        target = replace(target, text=target.text.replace("聚酯纖維", "聚酯纤维"))
    elif defect == "correctable_typo":
        target = replace(target, text=target.text.replace("COTTON", "C0TTON"))
    elif defect == "part":
        target = replace(target, selected_part="lining", parts={"lining": target.materials})
    elif defect == "missing_word":
        target = replace(target, image_words=target.image_words[:-1])
    elif defect == "extra_word":
        target = replace(target, image_words=target.image_words + (box("UNKNOWN", 20, 750, 150),))
    elif defect == "other_page":
        target = replace(target, image_words=tuple(replace(word, page=1) for word in target.image_words))
    else:
        words = list(target.image_words)
        words[8] = raw.image_words[8]
        target = replace(target, image_words=tuple(words))
    assert not recovery([raw, layout, target])


@pytest.mark.parametrize("defect", ["image", "variant", "source", "region", "changed_word", "extra_reason",
                                   "extra_part", "extra_material", "extra_ratio"])
def test_a_failed_layout_must_preserve_its_entire_original_response(defect):
    raw, layout, target = readings()
    if defect == "image":
        layout = replace(layout, image_key="other-label")
    elif defect == "variant":
        layout = replace(layout, image_variant_key="another-input")
    elif defect == "source":
        layout = replace(layout, source="preprocessed")
    elif defect == "region":
        layout = replace(layout, image_region=(0, 0, 2399, 2400))
    elif defect == "changed_word":
        layout = replace(layout, text=layout.text.replace("55", "5"))
    elif defect == "extra_reason":
        layout = replace(layout, rejected_composition_parts={"generic": ("unresolved_material_token",)})
    elif defect == "extra_part":
        layout = replace(layout, rejected_composition_parts={"lining": ("unpaired_material_rows",)})
    elif defect == "extra_material":
        layout = replace(layout, observed_materials=layout.observed_materials | {"generic": ["nylon"]})
    else:
        layout = replace(layout, observed_ratios=layout.observed_ratios | {"generic": [5]})
    assert not recovery([raw, layout, target])


def move(word, dx, dy):
    return replace(word, left=word.left + dx, right=word.right + dx,
                   top=word.top + dy, bottom=word.bottom + dy,
                   vertices=tuple((x + dx, y + dy) for x, y in word.vertices))


@pytest.mark.parametrize("defect", ["swapped_ratios", "second_curved_row", "numeric_footer_in_body",
                                   "warning_in_body", "prefix_in_body", "row_shift", "crossing_polygon"])
def test_changed_positions_and_incomplete_row_evidence_stay_rejected(defect):
    raw, layout, target = readings()
    words = list(raw.image_words)
    if defect == "swapped_ratios":
        words[2], words[6] = move(words[2], 330, 0), move(words[6], -330, 0)
    elif defect == "second_curved_row":
        old = words[17]
        words[17] = box(old.text, 640, 230, 180, local_angle=8)
    elif defect == "numeric_footer_in_body":
        words[-2] = move(words[-2], 0, -420)
    elif defect == "warning_in_body":
        words[-1] = move(words[-1], 0, -480)
    elif defect == "prefix_in_body":
        words[-4] = move(words[-4], 0, 230)
    elif defect == "row_shift":
        words[9:18] = [move(word, 0, 600) for word in words[9:18]]
    else:
        a, b, c, d = words[2].vertices
        words[2] = replace(words[2], vertices=(a, b, d, c))
    raw, layout = (replace(item, image_words=tuple(words)) for item in (raw, layout))
    assert not recovery([raw, layout, target])


@pytest.mark.parametrize("prefix", [("BRAND", "SKU1234-Z9"), ("STYLE NO:", "UNKNOWN"),
                                    ("STYLE NO:", "COTTON55"), ("SHELL:", "SKU1234-Z9")])
def test_only_a_labelled_nonmaterial_identifier_can_bound_the_top_context(prefix):
    assert not recovery(readings(prefix=prefix))


@pytest.mark.parametrize("footer", [
    ("38", "단추가 탈락되면 삼킬 수 있으므로 주의 하십시오."),
    ("100", "단추가 탈락되면 삼킬 수 있으므로 주의 하십시오."),
    ("384%", "단추가 탈락되면 삼킬 수 있으므로 주의 하십시오."),
    ("384", "UNKNOWN"), ("384", "OLEFIN"), ("384", "NYLON 5%"),
    ("384", "LINING COTTON 100%"), ("384", "임의 문구입니다."),
])
def test_extra_fibers_ratios_parts_and_unclassified_numbers_remain_evidence(footer):
    assert not recovery(readings(footer=footer))
