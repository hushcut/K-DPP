"""Keep all material cells while separating a proved, written care number."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.composition_region_recovery import recover_composition_region
from apps.text.ocr_candidates import build_candidate
from apps.text.ocr_corrections import _literal_name_tokens, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import _assess_candidates
from apps.text.parse_label import parse_label


def point(x, y, angle=0):
    theta = radians(angle)
    return (round(x * cos(theta) - y * sin(theta) + 1000),
            round(x * sin(theta) + y * cos(theta) + 1000))


def box(text, x, y, width, angle=0):
    vertices = tuple(point(a, b, angle) for a, b in
                     ((x, y), (x + width, y), (x + width, y + 24), (x, y + 24)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def readings(*, angle=0, temperature=30, japanese=True, ratios=(60, 35, 5), heading="品質表示"):
    names = ("ポリエステル", "レーヨン", "ポリウレタン") if japanese else ("POLYESTER", "RAYON", "POLYURETHANE")
    core = tuple(word for i, (name, ratio) in enumerate(zip(names, ratios)) for word in (
        box(name, 20, 120 + i * 110, 190, angle), box(str(ratio), 260, 120 + i * 110, 50, angle),
        box("%", 320, 120 + i * 110, 30, angle),
    ))
    header = (box(heading, 20, 50, 150, angle),)
    prefix = (box("チェスト 96 104", 20, -100, 290, angle), box("L", 350, -100, 30, angle))
    care_y = 510
    caption = box("手洗", 20, care_y, 100, angle)
    number = box(str(temperature), 50, care_y + 40, 50, angle)
    opaque = (box("中", 60, care_y + 110, 30, angle),
              box("サラン", 300, care_y, 100, angle), box("ライ", 480, care_y, 80, angle))
    other = (box("ドラ", 300, care_y, 80, angle), opaque[0], box("サラシ", 480, care_y, 100, angle))
    pairs = [f"{name} {ratio}%" for name, ratio in zip(names, ratios)]
    alternating = [line for name, ratio in zip(names, ratios) for line in (name, f"{ratio}%")]
    mixed = [names[0], names[1], f"{ratios[0]}%", f"{ratios[1]}%", names[2], f"{ratios[2]}%"]
    prefix_lines = ["チェスト 96 104", "L", heading]
    raw = prefix_lines + alternating + ["手洗", str(temperature), "中", "サラン", "ライ"]
    layout = prefix_lines + pairs + ["手洗", str(temperature), "中", "サラン", "ライ"]
    prep_raw = prefix_lines + alternating + ["ドラ", str(temperature), "中", "サラシ"]
    prep_layout = prefix_lines + pairs + ["ドラ", str(temperature), "中", "サラシ"]
    crop_points = tuple(point(x, y, angle) for x, y in ((-10, 40), (380, 40), (380, 410), (-10, 410)))
    xs, ys = zip(*crop_points)
    crop_region = (min(xs), min(ys), max(xs), max(ys))

    def candidate(source, text, words, used=False, region=(0, 0, 2600, 2600)):
        return replace(build_candidate(source, "\n".join(text), parse_candidate=parse_label, layout_used=used),
                       image_key="one-label", image_variant_key=source, image_words=words, image_region=region)

    original_words = prefix + header + core + (caption, number) + opaque
    prep_words = prefix + header + core + (number,) + other
    crop_words = header + core
    return [candidate("original", raw, original_words), candidate("original", layout, original_words, True),
            candidate("preprocessed", prep_raw, prep_words), candidate("preprocessed", prep_layout, prep_words, True),
            candidate("material_crop", [heading] + mixed, crop_words, region=crop_region),
            candidate("material_crop", [heading] + pairs, crop_words, True, crop_region)]


def recovery(item, items):
    return recover_composition_region(item, items[-1], "generic", items, tokenise=_literal_name_tokens)


@pytest.mark.parametrize("angle", [0, 6, -6, 90, -90])
@pytest.mark.parametrize("japanese", [False, True])
@pytest.mark.parametrize("temperature", [30, 40, 60])
def test_each_material_ratio_and_the_vertical_care_number_have_separate_evidence(angle, japanese, temperature):
    items = readings(angle=angle, japanese=japanese, temperature=temperature)
    assert items[-1].parser_status == "success"
    assert all(item.parser_status == "failed" for item in items[:-1])
    assert all(recovery(item, items) for item in items[:-1])
    assert all(same_region_recovery(item, items[-1], "generic", items) for item in items[:-1])
    decision = _assess_candidates(items)
    assert decision.status == "success"
    assert decision.best.materials == {"polyester": 60, "rayon": 35, "polyurethane": 5}
    assert decision.best.selected_part == "generic"


@pytest.mark.parametrize("ratios", [(55, 40, 5), (62.5, 32.5, 5)])
def test_ratios_are_read_from_cells_rather_than_completed_to_a_fixed_answer(ratios):
    items = readings(ratios=ratios)
    assert all(recovery(item, items) for item in items[:-1])
    assert _assess_candidates(items).best.materials == dict(zip(("polyester", "rayon", "polyurethane"), ratios))


def test_a_bare_number_without_the_original_written_caption_stays_unpaired():
    items = readings()[2:]
    assert not recovery(items[0], items)
    assert not recovery(items[1], items)


@pytest.mark.parametrize("defect", ["image", "same_variant", "same_source", "other_page", "full_region",
                                   "wrong_material", "wrong_ratio", "lost_annotation", "unknown_annotation"])
def test_a_different_or_incomplete_crop_cannot_supply_material_evidence(defect):
    items = readings()
    target = items[-1]
    if defect == "image":
        target = replace(target, image_key="different-label")
    elif defect == "same_variant":
        target = replace(target, image_variant_key=items[0].image_variant_key)
    elif defect == "same_source":
        target = replace(target, source=items[0].source)
    elif defect == "other_page":
        target = replace(target, image_words=tuple(replace(word, page=1) for word in target.image_words))
    elif defect == "full_region":
        target = replace(target, image_region=items[0].image_region)
    elif defect == "wrong_material":
        target = replace(target, text=target.text.replace("レーヨン", "綿"))
    elif defect == "wrong_ratio":
        target = replace(target, parts={"generic": {"polyester": 35, "rayon": 60, "polyurethane": 5}})
    elif defect == "lost_annotation":
        target = replace(target, image_words=target.image_words[:-1])
    else:
        target = replace(target, image_words=target.image_words + (box("UNKNOWN", 20, 390, 100),))
    items[-1] = target
    assert not recovery(items[0], items)


@pytest.mark.parametrize("defect", ["wrong_ratio", "extra_ratio", "extra_material", "other_part",
                                   "extra_reason", "missing_variant", "different_region", "lost_word"])
def test_original_conflicts_and_missing_provenance_are_not_discarded(defect):
    items = readings()
    source = items[0]
    if defect == "wrong_ratio":
        source = replace(source, observed_ratios={"generic": [60, 35, 5, 20]})
    elif defect == "extra_ratio":
        source = replace(source, observed_ratios={"generic": [60, 35, 5, 30, 40]})
    elif defect == "extra_material":
        source = replace(source, observed_materials={"generic": ["polyester", "rayon", "polyurethane", "cotton"]})
    elif defect == "other_part":
        source = replace(source, unpaired_ratio_parts=("outer",))
    elif defect == "extra_reason":
        source = replace(source, rejected_composition_parts={"generic": ("unresolved_material_token",)})
    elif defect == "missing_variant":
        source = replace(source, image_variant_key="")
    elif defect == "different_region":
        source = replace(source, image_region=(0, 0, 2500, 2600))
    else:
        source = replace(source, image_words=source.image_words[:-1])
    assert not recovery(source, items)


def moved(word, dx, dy):
    return replace(word, left=word.left + dx, right=word.right + dx, top=word.top + dy, bottom=word.bottom + dy,
                   vertices=tuple((x + dx, y + dy) for x, y in word.vertices))


@pytest.mark.parametrize("defect", ["ratio_swap", "row_swap", "inside_core", "care_intrusion", "caption_far",
                                   "number_far", "crossing_polygon", "lost_percent"])
def test_positions_cannot_borrow_a_number_or_hide_a_word(defect):
    items = readings()
    words = list(items[0].image_words)
    # prefix(2), heading(1), three 3-word rows, caption, number, opaque(3)
    if defect == "ratio_swap":
        words[4], words[7] = moved(words[4], 0, 110), moved(words[7], 0, -110)
    elif defect == "row_swap":
        words[3:6], words[6:9] = [moved(w, 0, 110) for w in words[3:6]], [moved(w, 0, -110) for w in words[6:9]]
    elif defect == "inside_core":
        words[-1] = moved(words[-1], 0, -280)
    elif defect == "care_intrusion":
        words[-1] = moved(words[-1], -430, 20)
    elif defect == "caption_far":
        words[12] = moved(words[12], -400, 0)
    elif defect == "number_far":
        words[13] = moved(words[13], 400, 0)
    elif defect == "crossing_polygon":
        a, b, c, d = words[4].vertices
        words[4] = replace(words[4], vertices=(a, b, d, c))
    else:
        words.pop(5)
    for i in (0, 1):
        items[i] = replace(items[i], image_words=tuple(words))
    assert not recovery(items[0], items)


def test_an_independent_number_must_match_the_proved_original_cell():
    items = readings()
    words = tuple(moved(word, 400, 0) if word.text == "30" else word for word in items[2].image_words)
    items[2] = replace(items[2], image_words=words)
    items[3] = replace(items[3], image_words=words)
    assert not recovery(items[2], items)


def replace_text(item, old, new):
    text = item.text.replace(old, new)
    words = tuple(replace(word, text=word.text.replace(old, new)) for word in item.image_words)
    parsed = build_candidate(item.source, text, parse_candidate=parse_label, layout_used=item.layout_used)
    return replace(parsed, image_key=item.image_key, image_variant_key=item.image_variant_key,
                   image_region=item.image_region, image_words=words)


@pytest.mark.parametrize("caption", ["手", "手洗?", "DRY CLEAN", "IRON", "HAND WASH UNKNOWN"])
def test_missing_partial_or_other_care_text_does_not_explain_the_number(caption):
    items = readings()
    items[:2] = [replace_text(item, "手洗", caption) for item in items[:2]]
    assert not recovery(items[0], items)
    assert not recovery(items[2], items)


@pytest.mark.parametrize("number", ["30%", "30?", "3O", "20", "30.5", "-30"])
def test_nonliteral_uncertain_or_unsupported_numbers_stay_evidence(number):
    items = readings(temperature=number)
    assert not recovery(items[0], items)
    assert not recovery(items[2], items)


@pytest.mark.parametrize("heading", ["MATERIALS", "素材", "纤维成分"])
def test_a_further_composition_section_cannot_be_hidden_as_care_footer(heading):
    items = readings()
    items[:2] = [replace_text(item, "ライ", heading) for item in items[:2]]
    items[2:4] = [replace_text(item, "サラシ", heading) for item in items[2:4]]
    assert not recovery(items[0], items)
    assert not recovery(items[2], items)


@pytest.mark.parametrize("extra", ["UNKNOWN", "OLEFIN", "COTTON 5%", "OUTER COTTON 100%"])
def test_unknown_fibers_extra_ratios_and_parts_are_not_silenced_below_the_table(extra):
    items = readings()
    items[:2] = [replace_text(item, "ライ", extra) for item in items[:2]]
    items[2:4] = [replace_text(item, "サラシ", extra) for item in items[2:4]]
    assert not recovery(items[0], items)
    assert not recovery(items[2], items)


def test_a_negating_word_cannot_be_absorbed_into_the_material_row():
    items = readings(japanese=False)
    altered = []
    for item in items:
        text = item.text.replace("POLYESTER", "NOT POLYESTER" if item.layout_used else "NOT\nPOLYESTER")
        words = tuple(replace(word, text="NOT POLYESTER") if word.text == "POLYESTER" else word
                      for word in item.image_words)
        parsed = build_candidate(item.source, text, parse_candidate=parse_label, layout_used=item.layout_used)
        altered.append(replace(parsed, image_key=item.image_key, image_variant_key=item.image_variant_key,
                               image_region=item.image_region, image_words=words))
    assert altered[-1].parser_status == "success"
    assert all(not recovery(item, altered) for item in altered[:-1])
    assert _assess_candidates(altered).status == "failed"


def footer_crop_readings(*, angle=0, temperature=30):
    """The reread now includes a literal caption/number, rather than clipping it."""
    from apps.text.table_care_recovery import verified_care_table_layout

    items = readings(angle=angle, temperature=temperature)
    old_crop = items[-1]
    words = old_crop.image_words + (
        box("手洗", 20, 510, 100, angle), box("イ", 120, 510, 20, angle),
        box(str(temperature), 50, 550, 50, angle))
    region = (0, 0, 2600, 2600)
    raw_text = items[-2].text + f"\n手洗イ\n{temperature}"
    layout_text = old_crop.text + f"\n手洗\nイ\n{temperature}"
    def parsed(text, used):
        return replace(build_candidate("material_crop", text, parse_candidate=parse_label, layout_used=used),
                       image_key=old_crop.image_key, image_variant_key=old_crop.image_variant_key,
                       image_words=words, image_region=region)
    raw, layout = parsed(raw_text, False), parsed(layout_text, True)
    rendered = verified_care_table_layout(raw, layout, tokenise=_literal_name_tokens)
    assert rendered is not None
    return items[:-2] + [raw, parsed(rendered, True)]


@pytest.mark.parametrize("angle", [-6, 0, 6])
@pytest.mark.parametrize("temperature", [30, 40, 60])
def test_verified_reread_footer_corroborates_the_same_full_image_care_cell(angle, temperature):
    items = footer_crop_readings(angle=angle, temperature=temperature)
    assert all(recovery(item, items) for item in items[:4])
    assert _assess_candidates(items).status == "success"


def test_reread_care_footer_requires_its_own_unmodified_raw_peer():
    items = footer_crop_readings()
    assert not recovery(items[0], items[:-2] + items[-1:])


def test_other_response_still_requires_the_original_written_caption():
    items = footer_crop_readings()
    items = items[2:]
    assert not recovery(items[0], items)


@pytest.mark.parametrize("shift", [(450, 0), (0, 300)])
def test_a_complete_care_cell_in_another_location_cannot_explain_this_number(shift):
    items = footer_crop_readings()
    for index in (-2, -1):
        item = items[index]
        words = tuple(moved(word, *shift) if word.text in {"手洗", "イ", "30"} else word
                      for word in item.image_words)
        items[index] = replace(item, image_words=words)
    assert not recovery(items[0], items)
