"""번역 계속 행과 좌표로 확인한 퍼센트 오독의 회귀 검사."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('translation', ['コットン', '棉', '면', 'хлопок'])
def test_registered_non_latin_translation_without_separator(translation):
    result = parse_label(f'Cotton 100%\n{translation}')
    assert result['status'] == 'success', result
    assert result['materials'] == {'cotton': 100}


def test_three_fibers_with_unseparated_japanese_translations():
    result = parse_label('62% Polyester\nポリエステル\n'
                         '33% Cotton\nコットン\n5% Elastane\nエラスタン')
    assert result['status'] == 'success', result
    assert result['materials'] == {'polyester': 62, 'cotton': 33, 'spandex': 5}


@pytest.mark.parametrize('text', [
    'Cotton 100%\nCoton',
    'Cotton 100%\nナイロン',
    'Cotton 100%\nコットン UNKNOWN',
    'Cotton 100%\nコットン OLEFIN',
    'Cotton 100%\nコットン 20%',
    'Cotton 100%\n10%\nコットン',
    'Cotton 60%\nLINING\nコットン\n40% Polyester',
    'Cotton 100%\nコットン\nMODACRYLIC 10%',
])
def test_translation_cannot_discard_other_fibers_ratios_or_parts(text):
    assert parse_label(text)['status'] == 'failed'


def readings(first='9596', second='596', target=(95, 5), percent=True):
    source_words = (
        OcrWord('Cotton', 10, 10, 70, 30), OcrWord(first, 80, 10, 125, 30),
        OcrWord('Span', 10, 40, 70, 60), OcrWord(second, 80, 40, 115, 60),
    )
    target_words = [OcrWord('Cotton', 10, 10, 70, 30),
                    OcrWord(str(target[0]), 80, 10, 100, 30),
                    OcrWord('Span', 10, 40, 70, 60),
                    OcrWord(str(target[1]), 80, 40, 90, 60)]
    suffix = '%' if percent else ''
    if percent:
        target_words.extend([OcrWord('%', 100, 10, 125, 30),
                             OcrWord('%', 90, 40, 115, 60)])
    common = {'image_key': 'same-image', 'image_transform': (1, 0, 0, 0, 1, 0),
              'image_region': (0, 0, 150, 80)}
    source_text = f'Cotton {first}\nSpan {second}'
    target_text = f'Cotton {target[0]}{suffix}\nSpan {target[1]}{suffix}'
    source = _build_payload_candidates('original', OcrPayload(
        source_text, layout_text=source_text, layout_words=source_words),
        image_variant_key='source', **common)[0]
    alternative = _build_payload_candidates('material_crop', OcrPayload(
        target_text, layout_text=target_text, layout_words=tuple(target_words)),
        image_variant_key='reread', **common)[0]
    return source, alternative


@pytest.mark.parametrize('first,second', [('9596', '596'), ('95%', '596')])
def test_same_region_percent_glyph_reread_is_used(first, second):
    source, alternative = readings(first, second)
    assert parse_label(source.text)['status'] == 'failed'
    assert alternative.parser_status == 'success'
    assert same_region_recovery(source, alternative, 'generic')
    decision = _assess_candidates([source, alternative])
    assert decision.status == 'success'
    assert decision.best.materials == {'cotton': 95, 'spandex': 5}


@pytest.mark.parametrize('first,second,target,percent', [
    ('9596%', '596', (95, 5), True),
    ('9596', '596%', (95, 5), True),
    ('9596', '596', (93, 7), True),
    ('9596', '596', (5, 95), True),
    ('9596', '596', (95, 5), False),
    ('995', '55', (95, 5), True),
    ('09596', '596', (95, 5), True),
    ('-9596', '596', (95, 5), True),
])
def test_percent_glyph_reread_cannot_guess_or_change_values(first, second, target, percent):
    source, alternative = readings(first, second, target, percent)
    assert not same_region_recovery(source, alternative, 'generic')
    assert _assess_candidates([source, alternative]).status == 'failed'


@pytest.mark.parametrize('failure', [
    'different_image', 'no_geometry', 'outside_region', 'moved_percent',
    'swapped_material_boxes', 'forged_pairs', 'unknown_fiber', 'extra_ratio',
    'different_part', 'duplicate_source_fiber',
])
def test_percent_glyph_recovery_requires_same_image_material_pair_and_position(failure):
    source, alternative = readings()
    if failure == 'different_image':
        alternative = replace(alternative, image_key='another-image')
    elif failure == 'no_geometry':
        source = replace(source, image_words=())
    elif failure == 'outside_region':
        alternative = replace(alternative, image_region=(0, 0, 100, 80))
    elif failure == 'moved_percent':
        alternative = replace(alternative, image_words=tuple(
            replace(word, left=130, right=145) if word.text == '%' else word
            for word in alternative.image_words))
    elif failure == 'swapped_material_boxes':
        alternative = replace(alternative, image_words=tuple(
            replace(word, top=40, bottom=60) if word.text == 'Cotton' else
            replace(word, top=10, bottom=30) if word.text == 'Span' else word
            for word in alternative.image_words))
    elif failure == 'forged_pairs':
        alternative = replace(alternative, parts={'generic': {'cotton': 5, 'spandex': 95}})
    elif failure == 'unknown_fiber':
        source = replace(source, text=source.text + '\nUNKNOWN 20%')
    elif failure == 'extra_ratio':
        source = replace(source, text=source.text + '\n20%', image_words=(
            *source.image_words, OcrWord('20%', 10, 65, 50, 75)))
    elif failure == 'different_part':
        alternative = replace(alternative, parts={'lining': alternative.parts['generic']})
        source = replace(source, text='OUTER\n' + source.text)
    else:
        source = replace(source, text=source.text + '\nCotton', image_words=(
            *source.image_words, OcrWord('Cotton', 10, 65, 70, 75)))
    part = 'outer' if failure == 'different_part' else 'generic'
    assert not same_region_recovery(source, alternative, part)
