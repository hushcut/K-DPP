"""통합 시 기존 복구와 새 검증 조건을 동시에 유지하는 경계 사례."""

import pytest

from apps.service.label_analysis import analyze_label_text


@pytest.mark.parametrize('text, material', [
    ('폴리우레딘 100%', 'polyurethane'),
    ('프리에스터 100%', 'polyester'),
    ('플리에스터 100%', 'polyester'),
    ('100% قطن', 'cotton'),
])
def test_existing_korean_repairs_and_new_arabic_names_coexist(text, material):
    result = analyze_label_text(text)
    assert result['status'] == 'success'
    assert result['materials'] == {material: 100}


@pytest.mark.parametrize('text', [
    '100% COTTON/COTON/CUSTOMFIBER/BAUMWOLLE',
    '80% COTTON/COTON/CUSTOMFIBER/BAUMWOLLE\n20% NYLON',
])
def test_opaque_long_translation_cannot_disappear(text):
    result = analyze_label_text(text)
    assert result['status'] == 'failed'
    assert result['materials'] == {}


def test_poly_project_policy_applies_to_a_complete_mixed_row():
    text = 'POLY 60% COTTON 40%'
    result = analyze_label_text(text)
    assert result['status'] == 'success'
    assert result['materials'] == {'polyester': 60, 'cotton': 40}
    assert result['confidence']['parser'] == 'medium'
    assert 'poly_abbreviation_as_polyester' in result['warnings']
    assert 'project_material_alias:poly:polyester' in result['warnings']
    assert 'confirmed_material_alias:poly:polyester' not in result['warnings']


@pytest.mark.parametrize('languages', [
    'UK:100% POLYESTER IT:100% POLIESTERE EL:100% ΠΟΛΥΕΣΤΕΡΑ',
    'FR:100% POLYESTER DE:100% POLYESTER IT:100% POLIESTERE CN:100% 聚酯纤维',
])
def test_unread_yarn_copy_requires_enough_literal_agreement(languages):
    result = analyze_label_text('YARN\n' + languages + ' JP:100% 刹工万元')
    assert result['status'] == 'failed'
    assert result['materials'] == {}
