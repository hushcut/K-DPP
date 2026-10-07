"""실제 DJ042 응답과 좌표·독립 입력·숫자·소재 보존 검사."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from apps.text import ocr_text
from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord, spatial_text_from_words
from apps.text.parse_label import parse_label


def build_response(item):
    words = tuple(OcrWord(w[0], *w[1:5], tuple(tuple(v) for v in w[5]), w[6]) for w in item['words'])
    return ocr_text._build_payload_candidates(item['source'],
        ocr_text.OcrPayload(item['text'], layout_text=item['layout_text'], layout_words=words),
        image_key=item['image_key'], image_variant_key=item['image_variant_key'],
        image_region=tuple(item['image_region']), image_transform=(1, 0, 0, 0, 1, 0))


@pytest.mark.parametrize('spelling', ['플리에스터', '플리 에스터', '프리 에스터'])
@pytest.mark.parametrize('ratio', ['50%', '50.0 %'])
def test_observed_complete_spelling_and_word_split_keep_ratio(spelling, ratio):
    result = parse_label('혼용률 면50% ' + spelling + ratio)
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 50, 'polyester': 50}


@pytest.mark.parametrize('text', [
    '플리에스터상품100%', '예시플리에스터100%', '플리 에스터상표100%',
    '면50% 플리에스터', '면50% 플리에스터-50%', '면50% 플리에스터49%',
    '면50% 플리에스터50% UNKNOWN5%', 'FAUX 플리에스터100%',
    '관리 에스터100%', '리에라의100%', '플리에스터80% MODACRYLIC20%',
])
def test_spelling_fix_keeps_missing_invalid_and_other_material_evidence(text):
    assert parse_label(text)['status'] == 'failed'


def assessed(candidates):
    decision = ocr_text._assess_candidates(candidates)
    return parse_label(decision.best.text, conflicting_parts=decision.conflicting_parts,
        unpaired_ratio_parts=decision.unpaired_ratio_parts,
        rejected_composition_parts=decision.rejected_composition_parts)


def test_complete_real_response_set_resolves_dj042_without_new_ocr():
    fixture = json.loads((Path(__file__).parent / 'fixtures/dj042_name_reread.json').read_text(encoding='utf-8'))
    candidates = [c for item in fixture['responses'] for c in build_response(item)]
    assert same_region_recovery(candidates[3], candidates[8], 'generic', candidates)
    assert same_region_recovery(candidates[6], candidates[8], 'generic', candidates)
    result = assessed(candidates)
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 50, 'polyester': 50}
    assert not result['warnings']


def response(source, name, *, y=50):
    words = (
        OcrWord('혼용률', 10, y, 95, y+30), OcrWord(':', 100, y, 105, y+30),
        OcrWord('면', 115, y, 130, y+30), OcrWord('50', 135, y, 165, y+30),
        OcrWord('%', 170, y, 180, y+30), OcrWord(name, 220, y, 305, y+30),
        OcrWord('50', 315, y, 345, y+30), OcrWord('%', 350, y, 360, y+30),
    )
    layout = spatial_text_from_words(list(words))
    return ocr_text._build_payload_candidates(source,
        ocr_text.OcrPayload(layout.replace(' %', '%'), layout_text=layout, layout_words=words),
        image_key='same-photo', image_variant_key=source + '-bytes', image_region=(0, 0, 400, 150), image_transform=(1, 0, 0, 0, 1, 0))


def case():
    source = response('original', '리에라의')
    target = response('crop-a', '폴리에스터')
    other = response('crop-b', '폴리에스터')
    return source, target, other


def test_two_independent_aligned_reads_restore_a_damaged_name():
    source, target, other = case()
    assert same_region_recovery(source[0], target[0], 'generic', source + target + other)


def test_raw_and_layout_of_one_response_are_not_independent_reads():
    source, target, _ = case()
    assert not same_region_recovery(source[0], target[0], 'generic', source + target)


@pytest.mark.parametrize('field,value', [('image_variant_key', 'same-bytes'), ('source', 'same-source')])
def test_independence_requires_distinct_bytes_and_sources(field, value):
    source, target, other = case()
    candidates = source + [replace(c, **{field: value}) for c in target + other]
    assert not same_region_recovery(source[0], candidates[2], 'generic', candidates)


@pytest.mark.parametrize('name', ['UNKNOWN', 'MODACRYLIC', '나일론', '레이온'])
def test_unknown_unpriced_and_different_known_fibers_remain_unresolved(name):
    source = response('original', name)
    target = response('crop-a', '폴리에스터')
    other = response('crop-b', '폴리에스터')
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)
    assert assessed(source + target + other)['status'] == 'failed'


def test_unregistered_korean_name_cannot_be_repaired_from_shape_alone():
    source = response('original', '나무섬유')
    target = response('crop-a', '폴리에스터')
    other = response('crop-b', '폴리에스터')
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)
    assert assessed(source + target + other)['status'] == 'failed'


def test_name_or_ratio_from_another_physical_row_cannot_confirm():
    source, target, _ = case()
    other = response('crop-b', '폴리에스터', y=110)
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)


def test_correct_read_from_another_photo_cannot_confirm():
    source, target, other = case()
    other = [replace(c, image_key='another-photo') for c in other]
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)


def test_missing_source_box_cannot_disappear_during_recovery():
    source, target, other = case()
    source = [replace(c, image_words=c.image_words[:-1]) for c in source]
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)


def test_source_boxes_outside_the_crop_cannot_recover():
    source, target, other = case()
    target = [replace(c, image_region=(110, 0, 400, 150)) for c in target]
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)


def test_valid_other_part_does_not_resolve_the_generic_fabric():
    source, target, other = case()
    target = [replace(c, parts={'lining': c.parts['generic']}, selected_part='lining') for c in target]
    assert not same_region_recovery(source[0], target[0], 'generic', source + target + other)


@pytest.mark.parametrize('change', ['extra_ratio', 'ratio_change', 'negative', 'extra_material', 'split_nylon', 'part_boundary'])
def test_source_numeric_and_material_changes_are_preserved(change):
    source, target, other = case()
    words = list(source[0].image_words)
    if change == 'extra_ratio':
        words.extend((OcrWord('5', 365, 50, 375, 80), OcrWord('%', 380, 50, 390, 80)))
    elif change == 'ratio_change':
        words[6] = replace(words[6], text='49')
    elif change == 'negative':
        words[6] = replace(words[6], text='-50')
    elif change == 'extra_material':
        words.append(OcrWord('나일론', 220, 100, 305, 130))
    elif change == 'split_nylon':
        words[5:6] = [OcrWord('나일', 220, 50, 260, 80), OcrWord('론', 261, 50, 305, 80)]
    else:
        words[0] = replace(words[0], text='안감')
    layout = spatial_text_from_words(words)
    modified = ocr_text._build_payload_candidates('original',
        ocr_text.OcrPayload(layout.replace(' %', '%'), layout_text=layout, layout_words=tuple(words)),
        image_key='same-photo', image_variant_key='original-bytes', image_region=(0, 0, 400, 150), image_transform=(1, 0, 0, 0, 1, 0))
    assert not same_region_recovery(modified[0], target[0], 'generic', modified + target + other)
    final = assessed(modified + target + other)
    if change == 'part_boundary':
        assert 'lining' in final['parse_evidence']['rejected_composition_parts']
    else:
        assert final['status'] == 'failed'
