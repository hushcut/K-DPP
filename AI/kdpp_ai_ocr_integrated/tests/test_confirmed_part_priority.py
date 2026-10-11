"""확정 부위 우선순위와 자수실 최하위 선택의 회귀 검증."""

import pytest

from apps.text.material_extraction import declared_part
from apps.text.ocr_text import _assess_candidates, _build_candidate
from apps.text.parse_label import PART_PRIORITY, parse_label
from apps.service.response_contract import LabelResponseContract


@pytest.mark.parametrize('heading,part', [
    ('겉감', 'outer'), ('', 'generic'), ('겉감2', 'outer_2'), ('안감', 'lining'),
    ('충전재', 'filling'), ('주머니감', 'pocket'), ('리브', 'rib'),
    ('소매', 'sleeve'), ('배색', 'color_block'), ('자수실', 'embroidery_yarn'),
])
def test_each_confirmed_part_precedes_or_becomes_the_yarn_fallback(heading, part):
    text = f'{heading} 면 100%\n자수 폴리에스터 100%' if heading != '자수실' else '자수실 면 100%'
    result = parse_label(text)
    assert result['status'] == 'success'
    assert result['selected_part'] == part
    assert result['materials'] == {'cotton': 100}
    assert result['materials'] == result['parts'][part]


@pytest.mark.parametrize('heading', [
    '자수', '자수실', '실', 'YARN', 'EMBROIDERY', 'EMBROIDERY YARN', 'EMBROIDERY THREAD',
    '刺绣', '刺繍',
])
def test_registered_yarn_headings_use_the_last_part(heading):
    result = parse_label(f'{heading}\n100% POLYESTER')
    assert result['status'] == 'success'
    assert result['selected_part'] == 'embroidery_yarn'
    assert result['materials'] == {'polyester': 100}
    assert PART_PRIORITY[-1] == 'embroidery_yarn'


@pytest.mark.parametrize('text', [
    '자수\nYARN\n실\n100% POLYESTER',
    '겉감 천연가죽(양가죽)\n안감 폴리에스터 100%\n배색 면 90% 폴리에스터 9% 폴리우레탄 1%',
    'OUTER UNKNOWN 100%\nLINING POLYESTER 100%',
    'OUTER COTTON 95%\nLINING POLYESTER 100%',
    'OUTER COTTON 100%\nPOLYESTER 100%\nLINING POLYESTER 100%',
])
def test_real_layouts_and_unconfirmed_higher_parts_select_only_verified_ratios(text):
    result = parse_label(text)
    assert result['status'] == 'success'
    part = 'embroidery_yarn' if text.startswith('자수') else 'lining'
    assert result['selected_part'] == part
    assert result['materials'] == {'polyester': 100}
    assert 'outer' not in result['parts']
    if part == 'lining':
        assert 'outer:composition_not_confirmed' in result['warnings']
        assert 'representative_part_fallback:lining' in result['warnings']
        assert 'outer' in result['parse_evidence']['rejected_composition_parts'] or any(
            warning.startswith('outer:') for warning in result['warnings'])


@pytest.mark.parametrize('text', [
    'YARN POLYESTER 100%\nOUTER COTTON 100%',
    'OUTER COTTON 100% YARN POLYESTER 100%',
    'COTTON 100%\nEMBROIDERY POLYESTER 100%',
    '면 100% (자수 폴리에스터 100%)',
])
def test_yarn_never_overwrites_a_confirmed_main_composition(text):
    result = parse_label(text)
    assert result['status'] == 'success'
    assert result['selected_part'] in ('outer', 'generic')
    assert result['materials'] == {'cotton': 100}


@pytest.mark.parametrize('text', [
    '자수 UNKNOWN 100%', '자수 폴리에스터 95%',
    '자수 폴리에스터 100%\n나일론 10%',
    '자수 폴리에스터 -100%', '자수 폴리에스터 150%',
    '자수 폴리에스터 100%\n자수 면 100%',
    'Adorable 40% Chic 30% Dream 30%',
])
def test_last_part_still_requires_a_complete_unambiguous_composition(text):
    result = parse_label(text)
    assert result['status'] == 'failed'
    assert result['materials'] == {}


@pytest.mark.parametrize('text', ['실크 100%', '실크100%'])
def test_short_thread_marker_does_not_split_silk(text):
    assert declared_part(text) is None
    result = parse_label(text)
    assert result['status'] == 'success'
    assert result['selected_part'] == 'generic'
    assert result['materials'] == {'silk': 100}


def test_candidate_metadata_keeps_unknown_main_separate_from_verified_lining():
    source = _build_candidate('original', 'UNKNOWN 100%\nLINING POLYESTER 100%')
    decision = _assess_candidates([source])
    assert decision.status == 'success'
    assert decision.best.selected_part == 'lining'
    assert 'generic' in decision.rejected_composition_parts
    assert 'lining' not in decision.rejected_composition_parts


def test_unlabelled_damage_cannot_be_hidden_by_an_outer_marker_in_another_candidate():
    source = _build_candidate('original', 'UNKNOWN 100%')
    target = _build_candidate('material_crop', 'OUTER POLYESTER 100%')
    decision = _assess_candidates([source, target])
    assert decision.status == 'failed'
    assert 'outer' in decision.rejected_composition_parts


def test_different_yarn_compositions_from_candidates_still_conflict():
    candidates = [_build_candidate('original', 'YARN POLYESTER 100%'),
                  _build_candidate('material_crop', 'YARN COTTON 100%')]
    result = _assess_candidates(candidates)
    assert result.status == 'failed'
    assert 'embroidery_yarn' in result.conflicting_parts


def test_unlocated_unknown_row_cannot_be_hidden_by_falling_back_to_another_candidate_lining():
    source = _build_candidate('original', 'OLEFIN 50%\nCOTTON 100%')
    target = _build_candidate('preprocessed', 'OUTER COTTON 100%\nLINING POLYESTER 100%')
    assert _assess_candidates([source, target]).status == 'failed'


@pytest.mark.parametrize('text,part', [
    ('YARN POLYESTER 100%', 'embroidery_yarn'),
    ('OUTER COTTON 95%\nLINING POLYESTER 100%', 'lining'),
])
def test_fallback_part_and_yarn_remain_valid_in_the_service_response_contract(text, part):
    response = LabelResponseContract.model_validate({'api_version': 'test', **parse_label(text)})
    assert response.status == 'success'
    assert response.selected_part == part
    assert response.materials == response.parts[part] == {'polyester': 100}


@pytest.mark.parametrize('caption', [
    '(자수, 상표, 무늬 등 제외)', '(심지, 밴드,\n자수장식 제외)',
    '( 심지 , 보강재 , 상표 , 무늬 , 밴드 ,\n자수 장식 제외 )',
    '(excluding embroidery)', '[embroidery decoration excluded]',
])
def test_exclusion_caption_does_not_create_a_yarn_part(caption):
    result = parse_label('OUTER POLYESTER 96% POLYURETHANE 4%\n' + caption)
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'polyester': 96, 'polyurethane': 4}
    assert 'embroidery_yarn' not in result['parts']
    assert 'embroidery_yarn' not in result['parse_evidence']['rejected_composition_parts']
