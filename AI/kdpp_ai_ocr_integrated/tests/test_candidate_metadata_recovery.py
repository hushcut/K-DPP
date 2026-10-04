from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _row_words
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def payload_candidates(material='Polyester', fragments=None, temperature='30', care=True):
    fragments = fragments or [material]
    boxes = [OcrWord('95', 10, 10, 45, 46), OcrWord('%', 45, 12, 65, 48)]
    for index, fragment in enumerate(fragments):
        boxes.append(OcrWord(fragment, 80 + index * 65, 14, 140 + index * 65, 58))
    boxes.extend([OcrWord('5', 10, 65, 35, 103), OcrWord('%', 35, 65, 65, 104),
                  OcrWord('Spandex', 80, 70, 210, 110),
                  OcrWord(temperature, 10, 170, 60, 205), OcrWord('AO', 80, 170, 120, 205)])
    raw = f'95% {material}\n5% Spandex\n{temperature}\nAO'
    layout = f'95 % {" ".join(fragments)}\n5 % Spandex\n{temperature} AO'
    if care:
        boxes.extend([OcrWord('HAND', 10, 225, 70, 245), OcrWord('WASH', 80, 225, 140, 245)])
        raw += '\nHAND\nWASH'
        layout += '\nHAND WASH'
    return _build_payload_candidates('original', OcrPayload(raw, layout_text=layout, layout_words=tuple(boxes)),
                                     image_key='same-image', image_variant_key='same-response',
                                     image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 400, 400))


@pytest.mark.parametrize('material,fragments', [
    ('Polyester', ['Polyester']),
    ('폴리에스터', ['폴리', '에스터']),
    ('ポリエステル', ['ポリエステル']),
    ('聚酯纤维', ['聚酯', '纤维']),
])
def test_same_response_care_row_resolves_bare_temperature(material, fragments):
    candidates = payload_candidates(material, fragments)
    assert candidates[0].parser_status == 'failed'
    assert candidates[1].parser_status == 'success'
    decision = _assess_candidates(candidates)
    assert decision.status == 'success'
    assert decision.best.materials == {'polyester': 95, 'spandex': 5}
    assert decision.unpaired_ratio_parts == ()


def test_percent_boxes_from_next_numeric_row_are_not_reused():
    candidates = payload_candidates()
    assert [word.text for word in _row_words('95% Polyester', candidates[0].image_words)] == ['95', '%', 'Polyester']


def test_two_percent_boxes_on_same_row_remain_evidence():
    candidates = payload_candidates()
    boxes = candidates[0].image_words + (OcrWord('%', 65, 12, 75, 48),)
    assert sum(word.text == '%' for word in _row_words('95% Polyester', boxes)) == 2
    assert _assess_candidates([replace(c, image_words=boxes) for c in candidates]).status == 'failed'


def test_wash_outline_in_same_response_does_not_need_missing_care_text():
    candidates = payload_candidates(temperature='130/', care=False)
    raw, layout = candidates
    candidates = _build_payload_candidates('original', OcrPayload(
        raw.text.replace('130/\nAO', 'AO\n130/'), layout_text=layout.text,
        layout_words=raw.image_words), image_key='same-image', image_variant_key='same-response',
        image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 400, 400))
    decision = _assess_candidates(candidates)
    assert candidates[0].parser_status == 'failed'
    assert decision.status == 'success'
    assert decision.best.materials == {'polyester': 95, 'spandex': 5}


@pytest.mark.parametrize('failure', [
    'no_geometry', 'different_image', 'different_response', 'different_source',
    'different_region', 'outside_region', 'removed_word', 'removed_percent',
    'added_percent', 'unknown_fiber', 'negative_ratio', 'swapped_pairs', 'different_part',
])
def test_care_recovery_preserves_tokens_pairs_image_and_part(failure):
    candidates = payload_candidates()
    raw, layout = candidates
    if failure == 'no_geometry':
        raw = replace(raw, image_words=())
    elif failure == 'different_image':
        layout = replace(layout, image_key='other-image')
    elif failure == 'different_response':
        layout = replace(layout, image_variant_key='other-response')
    elif failure == 'different_source':
        layout = replace(layout, source='preprocessed')
    elif failure == 'different_region':
        layout = replace(layout, image_region=(0, 0, 400, 300))
    elif failure == 'outside_region':
        raw = replace(raw, image_region=(0, 0, 400, 150))
        layout = replace(layout, image_region=raw.image_region)
    elif failure == 'removed_word':
        layout = replace(layout, text=layout.text.replace('AO', ''))
    elif failure == 'removed_percent':
        layout = replace(layout, text=layout.text.replace('95 %', '95'))
    elif failure == 'added_percent':
        raw = replace(raw, text=raw.text + '\n10%')
    elif failure == 'unknown_fiber':
        raw = replace(raw, text=raw.text.replace('Polyester', 'UNKNOWN'))
    elif failure == 'negative_ratio':
        raw = replace(raw, text=raw.text.replace('95%', '-95%'))
    elif failure == 'swapped_pairs':
        layout = replace(layout, parts={'generic': {'polyester': 5, 'spandex': 95}})
    else:
        raw, layout = _build_payload_candidates('original', OcrPayload(
            'OUTER\n' + raw.text, layout_text='OUTER\n' + layout.text,
            layout_words=(OcrWord('OUTER', 10, 0, 70, 8),) + raw.image_words), image_key='same-image',
            image_variant_key='same-response', image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 400, 400))
        layout = replace(layout, parts={'lining': layout.parts['outer']})
    assert _assess_candidates([raw, layout]).status == 'failed'


@pytest.mark.parametrize('temperature', ['30', '40', '50', '60', '70', '95'])
def test_bare_temperature_without_care_context_is_not_dismissed(temperature):
    assert _assess_candidates(payload_candidates(temperature=temperature, care=False)).status == 'failed'


@pytest.mark.parametrize('temperature', ['10', '30%', '-30', '300%', '30/40%'])
def test_non_wash_numbers_and_explicit_ratios_remain_rejected(temperature):
    assert _assess_candidates(payload_candidates(temperature=temperature)).status == 'failed'
