"""실사진에서 확인된 긴 소재명 오독과 보정 경계 검사."""

import pytest

from apps.text.material_extraction import normalize_text
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('name', ['폴리우레딘', '폴리 우 레딘'])
@pytest.mark.parametrize('ratio', ['6%', '6 %', '6.0%'])
def test_observed_polyurethane_spelling_retains_explicit_ratio(name, ratio):
    result = parse_label('혼용률 폴리에스터94%, ' + name + ratio)
    assert result['status'] == 'success', result
    assert result['materials'] == {'polyester': 94, 'polyurethane': 6}
    assert result['parse_evidence']['observed_ratios']['generic'] == [94.0, 6.0]


@pytest.mark.parametrize('text,expected', [
    ('혼용률 면50%, 프리에스터50%', {'cotton': 50, 'polyester': 50}),
    ('프리에스터 100%', {'polyester': 100}),
    ('폴리우레딘 100%', {'polyurethane': 100}),
])
def test_complete_observed_long_names_resolve_without_inserting_a_ratio(text, expected):
    result = parse_label(text)
    assert result['status'] == 'success', result
    assert result['materials'] == expected


@pytest.mark.parametrize('text', [
    '폴리에스터94%, 폴리우레딘',
    '폴리에스터94%, 폴리우레딘 -6%',
    '폴리에스터94%, 폴리우레딘 5%',
    '폴리에스터94%, 폴리우레딘 6% UNKNOWN 10%',
    '프리에스터80%, MODACRYLIC20%',
    '프리에스터80%, OLEFIN20%',
    'FAUX 프리에스터100%',
    '100% POLY',
    '관리 에스터 100%',
    '리에스터100%',
])
def test_spelling_fix_cannot_invent_missing_ratios_or_resolve_other_unknown_names(text):
    assert parse_label(text)['status'] == 'failed'


@pytest.mark.parametrize('name', ['프리에스터상품', '예시폴리우레딘제품'])
def test_longer_unregistered_words_do_not_become_materials(name):
    assert parse_label(name + '100%')['status'] == 'failed'


def test_unknown_rows_and_decimal_evidence_survive_normalization():
    text = 'UNKNOWN 3%\nPOLYURETHANE.5%\n프리에스터'
    normalized = normalize_text(text)
    assert 'unknown 3%' in normalized
    assert 'polyurethane.5%' in normalized
    assert normalized.endswith('폴리에스터')
