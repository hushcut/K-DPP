"""두 칸 표 라벨(부위 제목 | 조성)의 원문 순서가 부위 연결을 끊을 때의 후보 통합.

배포 서버에서 실패한 라벨은 사람이 보면 다음과 같다.

    겉감        면 100%
    안감        -

Vision 원문은 ``겉감 / 안감 / ... / 면 100%`` 순서라 원문 해석은 겉감을 비우고 면 100%를
안감에 붙인다. 같은 응답의 좌표 해석은 겉감과 면 100%를 한 행으로 묶어 성공한다. 같은
응답의 좌표로 그 행 연결이 증명될 때만 원문 순서가 남긴 겉감 누락 근거를 해소한다.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from apps.text import ocr_text
from apps.text.ocr_corrections import _verified_layout_rows, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.parse_label import parse_label

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/two_column_part_rows.json').read_text(encoding='utf-8'))
CASES = {case['case_id']: case for case in FIXTURE['cases']}
SOURCES = ('original', 'preprocessed', 'material_crop', 'material_crop_rotated')


def restore(data, *, text=None, words=None):
    flat_words = FIXTURE['word_sets'][data['words']]
    restored = words if words is not None else tuple(
        OcrWord(word, left, top, right, bottom, tuple(zip(flat[0::2], flat[1::2])))
        for word, left, top, right, bottom, flat in flat_words
    )
    candidate = ocr_text._build_candidate(
        data['source'], data['text'] if text is None else text, layout_used=data['layout_used'],
    )
    return replace(candidate, image_key=data['image_key'], image_variant_key=data['image_variant_key'],
                   image_words=restored, image_region=tuple(data['image_region']))


def candidates(case_id):
    return [restore(data) for data in CASES[case_id]['candidates']]


def pick(items, source, *, layout):
    return next(item for item in items if item.source == source and item.layout_used is layout)


def assessed(items):
    decision = ocr_text._assess_candidates(items)
    return parse_label(decision.best.text, conflicting_parts=decision.conflicting_parts,
                       unpaired_ratio_parts=decision.unpaired_ratio_parts,
                       rejected_composition_parts=decision.rejected_composition_parts)


def test_server_original_two_column_label_confirms_the_outer_row():
    result = assessed(candidates('server_original'))
    assert result['status'] == 'success', result
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': 100}


def test_raw_and_layout_of_one_response_confirm_the_outer_row():
    items = candidates('server_original')
    result = assessed([pick(items, 'original', layout=False), pick(items, 'original', layout=True)])
    assert result['status'] == 'success', result
    assert result['materials'] == {'cotton': 100}
    assert result['selected_part'] == 'outer'


def test_layout_readings_alone_keep_the_outer_row():
    result = assessed([item for item in candidates('server_original') if item.layout_used])
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 100}


def test_resized_copy_that_already_paired_the_row_stays_confirmed():
    result = assessed(candidates('server_small'))
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': 100}


@pytest.mark.parametrize('source', SOURCES)
def test_each_raw_reading_is_recovered_only_by_its_own_layout(source):
    items = candidates('server_original')
    raw = pick(items, source, layout=False)
    assert raw.rejected_composition_parts == {'outer': ('unpaired_material_rows',)}
    assert same_region_recovery(raw, pick(items, source, layout=True), 'outer', items)
    for other in SOURCES:
        if other != source:
            assert not same_region_recovery(raw, pick(items, other, layout=True), 'outer', items)


def test_changed_tokens_are_not_treated_as_one_response():
    items = candidates('server_original')
    raw = pick(items, 'original', layout=False)
    layout = pick(items, 'original', layout=True)
    data = next(d for d in CASES['server_original']['candidates'] if d['source'] == 'original' and d['layout_used'])
    added = restore(data, text=layout.text + '\nNYLON 20%')
    assert not same_region_recovery(raw, added, 'outer', items)


def test_composition_moved_off_the_heading_row_is_not_recovered():
    items = candidates('server_original')
    raw_data, layout_data = (next(d for d in CASES['server_original']['candidates']
                                  if d['source'] == 'original' and d['layout_used'] is layout)
                             for layout in (False, True))
    raw = pick(items, 'original', layout=False)
    heading = next(word for word in raw.image_words if word.text == '겉감')
    lining = next(word for word in raw.image_words if word.text == '안감')
    shift = lining.top - heading.top

    def lowered(word):
        if word.text not in {'면', '100', '%'}:
            return word
        return replace(word, top=word.top + shift, bottom=word.bottom + shift,
                       vertices=tuple((x, y + shift) for x, y in word.vertices))

    moved = tuple(lowered(word) for word in raw.image_words)
    moved_raw = restore(raw_data, words=moved)
    moved_layout = restore(layout_data, words=moved)
    assert not same_region_recovery(moved_raw, moved_layout, 'outer', [moved_raw, moved_layout])


def test_upside_down_composition_beside_an_upright_heading_is_not_recovered():
    """A folded tag can place inverted fiber words in the same box band as an upright heading."""
    items = candidates('server_original')
    raw_data, layout_data = (next(d for d in CASES['server_original']['candidates']
                                  if d['source'] == 'original' and d['layout_used'] is layout)
                             for layout in (False, True))
    raw = pick(items, 'original', layout=False)

    def inverted(word):
        if word.text not in {'면', '100', '%'}:
            return word
        top_left, top_right, bottom_right, bottom_left = word.vertices
        return replace(word, vertices=(bottom_right, bottom_left, top_left, top_right))

    flipped = tuple(inverted(word) for word in raw.image_words)
    flipped_raw = restore(raw_data, words=flipped)
    flipped_layout = restore(layout_data, words=flipped)
    assert _verified_layout_rows(flipped_layout), 'the grouping alone still pairs the row'
    assert not same_region_recovery(flipped_raw, flipped_layout, 'outer', [flipped_raw, flipped_layout])
    assert assessed([flipped_raw, flipped_layout])['status'] == 'failed'


def two_column_response(composition_words):
    """One synthetic response: an outer row and a bare lining heading below it."""
    words = (OcrWord('OUTER', 10, 10, 80, 30, ((10, 10), (80, 10), (80, 30), (10, 30))),
             *composition_words,
             OcrWord('LINING', 10, 60, 90, 80, ((10, 60), (90, 60), (90, 80), (10, 80))))
    row = ' '.join(word.text for word in composition_words)
    common = dict(image_key='synthetic', image_variant_key='synthetic', image_words=words,
                  image_region=(0.0, 0.0, 600.0, 200.0))
    raw = replace(ocr_text._build_candidate('original', f'OUTER\nLINING\n{row}'), **common)
    layout = replace(ocr_text._build_candidate('original', f'OUTER {row}\nLINING', layout_used=True), **common)
    return raw, layout


def boxed(text, left, right):
    return OcrWord(text, left, 10, right, 30, ((left, 10), (right, 10), (right, 30), (left, 30)))


@pytest.mark.parametrize(('row', 'recovered'), [
    ((('COTTON', 200, 280), ('80%', 290, 330), ('POLYESTER', 340, 450), ('20%', 460, 500)), True),
    ((('COTTON', 200, 280), ('POLYESTER', 290, 400), ('80%', 410, 450), ('20%', 460, 500)), False),
])
def test_recovered_row_needs_explicit_material_ratio_pairs(row, recovered):
    """A material column followed by a ratio column only guesses which fiber is 80%."""
    raw, layout = two_column_response(tuple(boxed(*word) for word in row))
    assert layout.parts == {'outer': {'cotton': 80, 'polyester': 20}}
    assert raw.rejected_composition_parts == {'outer': ('unpaired_material_rows',)}
    assert bool(same_region_recovery(raw, layout, 'outer', [raw, layout])) is recovered
    assert (assessed([raw, layout])['status'] == 'success') is recovered


def test_conflicting_outer_composition_from_another_response_stays_failed():
    items = candidates('server_original')
    data = next(d for d in CASES['server_original']['candidates']
                if d['source'] == 'preprocessed' and d['layout_used'])
    layout = pick(items, 'preprocessed', layout=True)
    conflicting = restore(data, text=layout.text.replace('면 100 %', '폴리에스터 100 %'))
    assert conflicting.parts == {'outer': {'polyester': 100}}
    result = assessed([conflicting if item is layout else item for item in items])
    assert result['status'] == 'failed'


def test_unexplained_ratio_under_the_raw_outer_heading_is_kept():
    """A wash temperature read as '30%' below the raw outer heading is still unpaired evidence."""
    items = candidates('chat_jpeg')
    raw = pick(items, 'original', layout=False)
    assert 'outer' in raw.unpaired_ratio_parts
    assert not same_region_recovery(raw, pick(items, 'original', layout=True), 'outer', items)
    assert assessed(items)['status'] == 'failed'
