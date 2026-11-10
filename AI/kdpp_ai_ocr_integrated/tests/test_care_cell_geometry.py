"""A care caption must have its own separate, aligned literal number cell."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from apps.text.care_cell_geometry import care_cell_clear, vertical_care_cell
from apps.text.ocr_layout import OcrWord


def box(text, x, y, width, height=20, *, angle=0, page=0):
    theta = radians(angle)
    vertices = tuple((round(px * cos(theta) - py * sin(theta) + 500),
                      round(px * sin(theta) + py * cos(theta) + 500))
                     for px, py in ((x, y), (x + width, y),
                                    (x + width, y + height), (x, y + height)))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices, page)


def cell(*, angle=0, number="30", x=25, y=32):
    return (box("手洗", 0, 0, 100, angle=angle),), box(number, x, y, 40, angle=angle)


@pytest.mark.parametrize("angle", [-90, -6, 0, 6, 90, 180])
@pytest.mark.parametrize("number", ["30", "40", "50", "60", "70", "95"])
def test_literal_bare_number_is_below_the_same_direction_caption(angle, number):
    caption, value = cell(angle=angle, number=number)
    assert vertical_care_cell(caption, value)
    assert care_cell_clear(caption + (value,), caption, value)


def test_multiword_caption_preserves_literal_reading_order():
    caption = (box("HAND", 0, 0, 45), box("WASH", 55, 0, 45))
    value = box("30", 30, 32, 40)
    assert vertical_care_cell(caption, value)
    assert not vertical_care_cell(tuple(reversed(caption)), value)


@pytest.mark.parametrize("number", ["30%", "30 °C", "35", "0", "100", "3O", "30/40", ""])
def test_no_percent_symbol_changed_digit_or_unsupported_number_is_inferred(number):
    caption, value = cell(number=number)
    assert not vertical_care_cell(caption, value)


@pytest.mark.parametrize("y", [-40, 0, 20, 21, 41, 100])
def test_touching_overlapping_above_or_distant_numbers_are_not_care_cells(y):
    caption, value = cell(y=y)
    assert not vertical_care_cell(caption, value)


def test_exact_maximum_gap_and_half_width_overlap_are_supported():
    caption = (box("手洗", 0, 0, 120),)
    assert vertical_care_cell(caption, box("30", 90, 40, 60))
    assert not vertical_care_cell(caption, box("30", 91, 40, 60))


def test_bottom_edge_uses_the_numbers_own_existing_physical_row_limit():
    caption, _ = cell()
    value = box("30", 25, 32, 40, angle=2)
    a, b, c, d = value.vertices
    vertices = (a, b, (c[0], c[1] + 2), d)
    ys = tuple(y for _x, y in vertices)
    value = replace(value, top=min(ys), bottom=max(ys), vertices=vertices)
    assert vertical_care_cell(caption, value)


@pytest.mark.parametrize("defect", ["number_page", "caption_page", "missing_number_vertices",
                                   "missing_caption_vertices", "zero_edge", "self_crossing",
                                   "number_opposite", "number_tilt", "two_caption_rows"])
def test_each_required_annotation_has_valid_same_page_reading_geometry(defect):
    caption, value = cell()
    if defect == "number_page":
        value = replace(value, page=1)
    elif defect == "caption_page":
        caption = (replace(caption[0], page=1),)
    elif defect == "missing_number_vertices":
        value = replace(value, vertices=())
    elif defect == "missing_caption_vertices":
        caption = (replace(caption[0], vertices=()),)
    elif defect == "zero_edge":
        value = replace(value, vertices=((value.left, value.top),) * 4)
    elif defect == "self_crossing":
        a, b, c, d = value.vertices
        value = replace(value, vertices=(a, c, b, d))
    elif defect == "number_opposite":
        a, b, c, d = value.vertices
        value = replace(value, vertices=(b, a, d, c))
    elif defect == "number_tilt":
        value = box("30", 25, 32, 40, angle=8)
    else:
        caption = (box("HAND", 0, 0, 45), box("WASH", 55, 30, 45))
    assert not vertical_care_cell(caption, value)


@pytest.mark.parametrize("kind", ["word", "extra_number", "extra_material"])
def test_another_annotation_inside_the_cell_is_never_silently_ignored(kind):
    caption, value = cell()
    text = {"word": "MYSTERY", "extra_number": "40", "extra_material": "COTTON"}[kind]
    intruder = box(text, 10, 25, 25, 5)
    assert not care_cell_clear(caption + (value, intruder), caption, value)


def test_explicitly_proved_same_place_annotations_can_be_allowed():
    caption, value = cell()
    reread = replace(value, left=value.left + 1, right=value.right + 1,
                     vertices=tuple((x + 1, y) for x, y in value.vertices))
    assert not care_cell_clear((reread,), caption, value)
    assert care_cell_clear((reread,), caption, value, allowed_words=(reread,))


def test_only_positive_area_intersections_are_intrusions():
    caption, value = cell()
    touching = box("OTHER", 100, 0, 20)
    outside = box("OTHER", 120, 0, 20)
    penetrating = box("OTHER", 99, 0, 20)
    assert care_cell_clear((touching, outside), caption, value)
    assert not care_cell_clear((penetrating,), caption, value)


def test_reference_cell_needs_a_nonempty_caption_and_one_page():
    caption, value = cell()
    assert not vertical_care_cell((), value)
    assert not care_cell_clear((), (), value)
    assert not care_cell_clear((replace(value, page=1),), caption, value)
