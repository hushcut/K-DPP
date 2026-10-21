"""Integer box edges need a bounded pixel allowance beside angular tolerance."""
from collections import Counter
from dataclasses import replace
from random import Random

import pytest

from apps.text.ocr_layout import OcrWord, _aligned_with_slope, spatial_text_from_words
from apps.text.parse_label import parse_label


def box(text, x, y, width, *, slope=-0.22, height=28, edge_noise=0, offset=(0, 0)):
    top = round(y + slope * x)
    dy = round(slope * width) + edge_noise
    points = ((x, top), (x + width, top + dy),
              (x + width, top + dy + height), (x, top + height))
    vertices = tuple((px + offset[0], py + offset[1]) for px, py in points)
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def table(slope=-0.22, offset=(0, 0)):
    kwargs = {'slope': slope, 'offset': offset}
    words = [box('OUTER', 20, 240, 110, **kwargs)]
    for index, (name, ratio) in enumerate((('綿', 57), ('NYLON', 31), ('ACRYLIC', 12))):
        y = 300 + index * 50
        words += [box(name, 20, y, 38 if index == 0 else 200,
                      edge_noise=(-3 if slope < 0 else 3) if index == 0 else 0, **kwargs),
                  box(str(ratio), 650, y, 34, **kwargs), box('%', 688, y, 20, **kwargs)]
    footer_y = 436 + max(0, slope) * 710
    words += [box('CAPTION', 20, footer_y, 100, slope=0, offset=offset),
              box('DETAILS', 140, footer_y, 120, slope=0, offset=offset)]
    return words


@pytest.mark.parametrize('slope', [-0.22, 0.22])
@pytest.mark.parametrize('offset', [(0, 0), (137, 91)])
@pytest.mark.parametrize('seed', [0, 1, 2])
def test_short_box_at_angular_boundary_keeps_the_complete_local_row(slope, offset, seed):
    words = table(slope, offset)
    Random(seed).shuffle(words)
    layout = spatial_text_from_words(words)
    assert layout == 'OUTER\n綿 57 %\nNYLON 31 %\nACRYLIC 12 %\nCAPTION DETAILS'
    assert Counter(layout.split()) == Counter(w.text for w in words)
    assert parse_label(layout)['materials'] == {'cotton': 57, 'nylon': 31, 'acrylic': 12}


@pytest.mark.parametrize('text', ['綿', 'X', '13', '%', 'OPAQUE'])
def test_pixel_allowance_does_not_depend_on_material_or_ratio_text(text):
    value = box(text, 20, 300, 38, edge_noise=-3)
    assert not _aligned_with_slope(value, -0.22)
    assert _aligned_with_slope(value, -0.22, allow_quantisation=True)
    assert not _aligned_with_slope(box(text, 20, 300, 38, edge_noise=-4), -0.22, allow_quantisation=True)


@pytest.mark.parametrize('defect', ['missing', 'degenerate', 'opposite', 'flat', 'excess_top', 'excess_bottom'])
def test_pixel_allowance_still_requires_both_valid_aligned_edges(defect):
    words = table()
    old = words[1]
    if defect == 'missing':
        changed = replace(old, vertices=())
    elif defect == 'degenerate':
        changed = replace(old, vertices=((0, 0),) * 4)
    elif defect in {'opposite', 'flat'}:
        changed = box(old.text, 20, 300, 38, slope=0.22 if defect == 'opposite' else 0)
    else:
        points = list(old.vertices)
        index = 1 if defect == 'excess_top' else 2
        x, y = points[index]
        points[index] = (x, y - 2)
        changed = replace(old, vertices=tuple(points))
    words[1] = changed
    assert not _aligned_with_slope(changed, -0.22, allow_quantisation=True)
    layout = spatial_text_from_words(words)
    assert Counter(layout.split()) == Counter(w.text for w in words)
    assert '綿 57 %' not in layout


@pytest.mark.parametrize('slope,edge_direction', [(-0.22, 0), (-0.22, 1), (0.22, 0), (0.22, -1)])
def test_one_pixel_allowance_cannot_establish_the_direction_of_a_one_pixel_edge(slope, edge_direction):
    value = box('X', 20, 300, 1, edge_noise=edge_direction)
    assert not _aligned_with_slope(value, slope, allow_quantisation=True)


def test_restored_layout_keeps_an_unregistered_fiber_rejected():
    words = [replace(w, text='OLEFIN') if w.text == 'NYLON' else w for w in table()]
    layout = spatial_text_from_words(words)
    assert 'OLEFIN 31 %' in layout
    assert parse_label(layout)['status'] == 'failed'


def test_distant_or_other_page_numbers_cannot_join_the_restored_row():
    for defect in ('distant', 'other_page'):
        words = table()
        number = words[2]
        if defect == 'distant':
            words[2] = replace(number, top=number.top - 200, bottom=number.bottom - 200,
                               vertices=tuple((x, y - 200) for x, y in number.vertices))
        else:
            words[2] = replace(number, page=1)
        assert '綿 57 %' not in spatial_text_from_words(words)
