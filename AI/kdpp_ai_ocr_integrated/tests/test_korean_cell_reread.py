"""Independent partial reads must confirm every physical material cell."""

from dataclasses import replace

import pytest

from apps.text import ocr_text
from apps.text.ocr_corrections import _same_region_korean_cell_recovery
from apps.text.ocr_layout import OcrWord


def response(source, *, name='폴리에스터', first='면', heading='혼용률',
             ratios=('60', '40'), extra=(), y=50, polygons=True, bad_layout=False):
    values = [(heading, 10, 95), (':', 100, 105)]
    if first:
        values.append((first, 115, 130))
    values.extend([(ratios[0], 135, 165), ('%', 170, 180),
                   (name, 220, 305), (ratios[1], 315, 345), ('%', 350, 360)])
    words = tuple(OcrWord(text, left, y, right, y + 30,
                         ((left, y), (right, y), (right, y + 30), (left, y + 30)) if polygons else ())
                  for text, left, right in values) + tuple(extra)
    raw = ' '.join(w.text for w in words)
    layout = raw
    if bad_layout:
        raw += '\n제조국: 한국'
        words += (OcrWord('제조국:', 10, y + 50, 95, y + 80,
                         ((10, y + 50), (95, y + 50), (95, y + 80), (10, y + 80))),
                  OcrWord('한국', 100, y + 50, 130, y + 80,
                         ((100, y + 50), (130, y + 50), (130, y + 80), (100, y + 80))))
        layout = raw.replace('40 %\n제조국: 한국', '\n제조국: 한국 40 %')
    return ocr_text._build_payload_candidates(source, ocr_text.OcrPayload(
        raw.replace(' %', '%'), layout_text=layout, layout_words=words), image_key='same-photo',
        image_variant_key=source + '-bytes', image_region=(0, 0, 500, 250),
        image_transform=(1, 0, 0, 0, 1, 0))


def case(**kwargs):
    a = response('original', name='관리에스터', **kwargs)
    b = response('contrast', name='관리에스터', **kwargs)
    target = response('crop', heading='혼용품', **kwargs)
    partial = response('rotated-crop', first='', bad_layout=True, **kwargs)
    return a, b, target, partial


def recovered(source, target, candidates):
    return _same_region_korean_cell_recovery(source, target, 'generic', candidates)


@pytest.mark.parametrize('ratios', [('60', '40'), ('50', '50'), ('70', '30')])
def test_each_cell_can_be_confirmed_without_two_complete_reads(ratios):
    a, b, target, _ = case(ratios=ratios)
    partial = response('rotated-crop', first='', ratios=ratios)
    candidates = a + b + target + partial
    assert recovered(a[0], target[0], candidates)
    assert recovered(partial[0], target[0], candidates)
    decision = ocr_text._assess_candidates(candidates)
    assert decision.status == 'success'
    assert decision.best.materials == {'cotton': int(ratios[0]), 'polyester': int(ratios[1])}


def test_layout_percentage_in_metadata_needs_token_preserving_raw_row():
    a, b, target, partial = case(ratios=('50', '50'))
    candidates = a + b + target + partial
    assert recovered(partial[1], target[0], candidates)
    assert ocr_text._assess_candidates(candidates).status == 'success'


def test_layout_pair_that_changes_a_known_ratio_is_not_released():
    a, b, target, partial = case()
    assert not recovered(partial[1], target[0], a + b + target + partial)


@pytest.mark.parametrize('mutation', [
    'same_bytes', 'same_source', 'other_photo', 'other_row', 'no_geometry',
    'different_part', 'missing_percent', 'missing_box', 'outside_region',
    'different_ratio', 'extra_ratio', 'unknown', 'known_other_fiber',
    'split_other_fiber', 'signed_ratio', 'invented_layout', 'duplicate_box',
    'reversed_polygon', 'nonparallel_polygon',
])
def test_partial_evidence_cannot_remove_conflicting_or_unlocated_tokens(mutation):
    a, b, target, partial = case()
    if mutation == 'same_bytes':
        partial = [replace(c, image_variant_key=target[0].image_variant_key) for c in partial]
    elif mutation == 'same_source':
        partial = [replace(c, source=target[0].source) for c in partial]
    elif mutation == 'other_photo':
        partial = [replace(c, image_key='other-photo') for c in partial]
    elif mutation == 'other_row':
        partial = response('rotated-crop', first='', y=160)
    elif mutation == 'different_part':
        target = [replace(c, parts={'lining': c.parts['generic']}) for c in target]
    elif mutation == 'outside_region':
        target = [replace(c, image_region=(200, 0, 500, 250)) for c in target]
    elif mutation == 'no_geometry':
        a = [replace(c, image_words=tuple(replace(w, vertices=()) for w in c.image_words)) for c in a]
    elif mutation == 'missing_box':
        a = [replace(c, image_words=c.image_words[:-1]) for c in a]
    elif mutation == 'duplicate_box':
        a = [replace(c, image_words=c.image_words + (c.image_words[-1],)) for c in a]
    elif mutation in ('reversed_polygon', 'nonparallel_polygon'):
        w = a[0].image_words[6]
        vertices = tuple(reversed(w.vertices)) if mutation == 'reversed_polygon' else (
            (220, 50), (305, 50), (305, 80), (220, 100))
        a = [replace(c, image_words=c.image_words[:6] + (replace(w, vertices=vertices),) + c.image_words[7:]) for c in a]
    elif mutation == 'invented_layout':
        partial = [partial[0], replace(partial[1], text=partial[1].text + ' 면')]
    else:
        values = {
            'different_ratio': {'ratios': ('59', '40')},
            'signed_ratio': {'ratios': ('-60', '40')},
            'unknown': {'name': 'UNKNOWN'},
            'known_other_fiber': {'name': '나일론'},
            'split_other_fiber': {'name': '나일 론'},
            'extra_ratio': {'extra': (OcrWord('5%', 380, 50, 400, 80,
                                          ((380, 50), (400, 50), (400, 80), (380, 80))),)},
            'missing_percent': {'ratios': ('60', '40')},
        }
        a = response('original', **values[mutation])
        if mutation == 'missing_percent':
            a = [replace(c, text=c.text.replace('40 %', '40'),
                         image_words=c.image_words[:-1]) for c in a]
    candidates = a + b + target + partial
    assert not recovered(a[0], target[0], candidates)


def test_one_character_name_needs_two_other_responses_at_its_cell():
    _, _, target, partial = case()
    assert not recovered(partial[0], target[0], target + partial)


@pytest.mark.parametrize('name', ['UNKNOWN', '나무섬유', '나일론'])
def test_present_unregistered_or_different_name_is_never_an_empty_cell(name):
    a, b, target, _ = case()
    partial = response('rotated-crop', first=name)
    assert not recovered(partial[0], target[0], a + b + target + partial)
