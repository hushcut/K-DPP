from dataclasses import replace

import pytest

from apps.text.ocr_corrections import _annotation_tokens, _row_words, _tokens
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
    # The row has one printed percent token but two same-row boxes. Complete
    # annotation proof rejects this ambiguity rather than hiding either box.
    assert _row_words('95% Polyester', boxes) == ()
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


@pytest.mark.parametrize('extra', ['FOO', 'FOO BAR', '魚&', 'OLEFIN', 'FAUX', '인조', '未知繊維'])
def test_same_response_temperature_cannot_hide_preserved_opaque_or_forbidden_context(extra):
    raw, layout = payload_candidates()
    boxes = raw.image_words + (OcrWord(extra, 10, 280, 180, 310),)
    candidates = _build_payload_candidates('original', OcrPayload(
        raw.text + '\n' + extra, layout_text=layout.text + '\n' + extra, layout_words=boxes),
        image_key=raw.image_key, image_variant_key=raw.image_variant_key,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=raw.image_region)
    assert _assess_candidates(candidates).status == 'failed'


@pytest.mark.parametrize('extra', ['FOO', 'FOO BAR', '魚&', 'OLEFIN', 'FAUX', '인조', '未知繊維'])
def test_general_alphanumeric_metadata_does_not_supply_a_wash_row_proof(extra):
    raw, layout = payload_candidates()
    boxes = tuple(replace(word, text=extra, right=210) if word.text == 'AO' else word
                  for word in raw.image_words)
    candidates = _build_payload_candidates('original', OcrPayload(
        raw.text.replace('AO', extra), layout_text=layout.text.replace('AO', extra), layout_words=boxes),
        image_key=raw.image_key, image_variant_key=raw.image_variant_key,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=raw.image_region)
    assert _assess_candidates(candidates).status == 'failed'


@pytest.mark.parametrize('failure', ['missing_character', 'extra_character', 'multiple_pages',
                                   'swapped_physical_materials', 'missing_care_box'])
def test_metadata_recovery_requires_complete_characters_and_physical_material_pairs(failure):
    raw, layout = payload_candidates('폴리에스터', ['폴리', '에스터'])
    if failure == 'missing_character':
        boxes = tuple(replace(word, text='에스') if word.text == '에스터' else word for word in raw.image_words)
    elif failure == 'extra_character':
        boxes = tuple(replace(word, text='에스터X') if word.text == '에스터' else word for word in raw.image_words)
    elif failure == 'multiple_pages':
        boxes = tuple(replace(word, page=1) if word.text == 'AO' else word for word in raw.image_words)
    elif failure == 'swapped_physical_materials':
        boxes = tuple(replace(word, top=70, bottom=110) if word.text in {'폴리', '에스터'} else
                      replace(word, top=14, bottom=58) if word.text == 'Spandex' else word for word in raw.image_words)
    else:
        boxes = tuple(word for word in raw.image_words if word.text != 'WASH')
    assert _assess_candidates([replace(raw, image_words=boxes), replace(layout, image_words=boxes)]).status == 'failed'


def test_coordinate_character_tokenisation_preserves_semantic_negation_and_whole_digits():
    assert _tokens('인조 未知繊維 95 -0.5%') == ('인조', '未知繊維', '95', '-', '0', '.', '5', '%')
    assert _annotation_tokens('인조 未知繊維 95 -0.5%') == (
        '인', '조', '未', '知', '繊', '維', '95', '-', '0', '.', '5', '%',
    )
