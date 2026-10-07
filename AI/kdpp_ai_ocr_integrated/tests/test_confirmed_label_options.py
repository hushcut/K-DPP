"""사진별 확인 옵션·기본 엄격 판정·미등록 이름 개수 우회 회귀."""

import json
from pathlib import Path

import pytest

from apps.service.label_analysis import analyze_label_text
from apps.text import ocr_text
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('text', ['POLY 100%', '100 % POLY', 'poly 100％'])
def test_confirmed_poly_is_opt_in_and_retains_original_text(text):
    assert parse_label(text)['status'] == 'failed'
    result = analyze_label_text(text, confirmed_polyester_poly=True)
    assert result['status'] == 'success'
    assert result['materials'] == {'polyester': 100}
    assert result['raw_ocr_preview'] == text
    assert result['confidence']['ocr'] == 'unknown'
    assert 'confirmed_material_alias:poly:polyester' in result['warnings']
    assert parse_label(text)['status'] == 'failed'


@pytest.mark.parametrize('text', [
    'POLY -100%', 'POLY 99%', 'POLY 101%', 'POLY', 'POLY 100% UNKNOWN5%',
    'POLYMODACRYLIC 100%', 'POLYAMIDE 80% MODACRYLIC20%', 'FAUX POLY100%',
])
def test_confirmation_never_repairs_numbers_unknown_fibers_or_partial_words(text):
    assert parse_label(text, confirmed_polyester_poly=True)['status'] == 'failed'


@pytest.mark.parametrize('text,expected', [
    ('POLYAMIDE 100%', {'nylon': 100}),
    ('POLYURETHANE 100%', {'polyurethane': 100}),
])
def test_complete_other_poly_fibers_keep_their_own_identity(text, expected):
    assert parse_label(text, confirmed_polyester_poly=True)['materials'] == expected


def test_first_composition_requires_confirmation_and_keeps_second_evidence():
    text = 'MATERIAL\nCOTTON 80%\nNYLON 20%\nPOLYESTER 100%'
    assert parse_label(text)['status'] == 'failed'
    result = analyze_label_text(text, confirmed_first_generic=True)
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 80, 'nylon': 20}
    assert result['parts']['generic_secondary'] == {'polyester': 100}
    assert 'confirmed_representative_selection:first_generic' in result['warnings']
    assert result['raw_ocr_preview'] == text.replace('\n', ' ')


@pytest.mark.parametrize('text', [
    'MATERIAL\nCOTTON80%\nNYLON19%\nPOLYESTER100%',
    'MATERIAL\nUNKNOWN20%\nCOTTON80%\nPOLYESTER100%',
    'MATERIAL\nCOTTON100%\nUNKNOWN5%',
    'MATERIAL\nCOTTON100%\n5%',
    'MATERIAL\nCOTTON-80%\nNYLON20%\nPOLYESTER100%',
])
def test_first_selection_cannot_repair_the_selected_block_or_hide_one_extra_ratio(text):
    assert parse_label(text, confirmed_first_generic=True)['status'] == 'failed'


def test_first_selection_does_not_change_explicit_part_priority():
    text = 'LINING POLYESTER100%\nOUTER COTTON100%'
    result = parse_label(text, confirmed_first_generic=True)
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': 100}
    assert 'confirmed_representative_selection:first_generic' not in result['warnings']


@pytest.mark.parametrize('option', ['confirmed_first_generic', 'confirmed_polyester_poly'])
@pytest.mark.parametrize('value', ['false', 1, None])
def test_confirmation_options_reject_truthy_non_booleans(option, value):
    with pytest.raises(ValueError):
        parse_label('POLY100%', **{option: value})


@pytest.mark.parametrize('name', ['나무섬유', '대나무', '새로운섬유', '리에라의'])
def test_counts_alone_never_supply_a_missing_fiber_name(name):
    candidates = [ocr_text._build_candidate('original', '혼용률 면50% ' + name + '50%'),
                  ocr_text._build_candidate('crop', '혼용률 면50% 폴리에스터50%')]
    decision = ocr_text._assess_candidates(candidates)
    result = parse_label(decision.best.text, conflicting_parts=decision.conflicting_parts,
                         unpaired_ratio_parts=decision.unpaired_ratio_parts,
                         rejected_composition_parts=decision.rejected_composition_parts)
    assert result['status'] == 'failed'


def test_saved_confirmed_photos_are_reviewed_without_truth_injection():
    fixture = json.loads((Path(__file__).parent / 'fixtures/confirmed_label_options.json').read_text(encoding='utf-8'))
    expected = {'DJ002': {'polyester': 100}, 'DJ019': {'polyester': 100},
                'DJ009': {'rayon': 45, 'nylon': 28, 'polyester': 22, 'polyurethane': 5}}
    for item in fixture['responses']:
        assert parse_label(item['text'])['status'] == 'failed'
        result = analyze_label_text(item['text'], **item['confirmed_options'])
        assert result['status'] == 'success'
        assert result['materials'] == expected[item['image_id']]
        assert result['confidence']['ocr'] == 'unknown'
        if item['image_id'] == 'DJ009':
            assert 'generic_secondary' in result['parse_evidence']['rejected_composition_parts']
