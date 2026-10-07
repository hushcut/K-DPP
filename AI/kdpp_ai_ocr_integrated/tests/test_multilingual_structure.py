"""명시 조성 블록의 등록 번역과 라벨 번호·세탁 안내 경계 회귀."""

import pytest

from apps.text.parse_label import build_line_infos, parse_label


@pytest.mark.parametrize('text', [
    'Composition\nCotton 100%\nCoton\nBaumwolle\nAlgodón',
    'Composition\n100%\nCotton\nCoton\nBaumwolle',
    'Composition\nCotton\nCoton\nBaumwolle\n100%',
    'OUTER\nCotton 100%\nCoton\nBaumwolle\nLINING\nNylon 100%',
])
def test_registered_latin_translations_belong_to_one_explicit_composition(text):
    result = parse_label(text)
    assert result['status'] == 'success', result
    assert result['materials'] == {'cotton': 100}


def test_each_fiber_keeps_its_ratio_and_translation_rows():
    result = parse_label('Composition\nPolyester 62%\nPoliéster\nPolyestere\n'
                         'Cotton 33%\nCoton\nBaumwolle\n'
                         'Elastane 5%\nElasthan\nElastano')
    assert result['status'] == 'success', result
    assert result['materials'] == {'polyester': 62, 'cotton': 33, 'spandex': 5}
    assert result['parse_evidence']['observed_ratios']['generic'] == [62.0, 33.0, 5.0]


@pytest.mark.parametrize('suffix', [
    'Nylon', 'UNKNOWN', 'OLEFIN', 'UNKNOWN FIBER', 'OLEFIN FIBRE',
    'HAND WASH OLEFIN', 'MODACRYLIC 10%', 'Coton 20%', '10%',
    'Polyester 30%', 'Coton -5%',
])
def test_registered_translation_run_does_not_erase_other_evidence(suffix):
    result = parse_label('Composition\nCotton 100%\nCoton\nBaumwolle\n' + suffix)
    assert result['status'] == 'failed', result


def test_known_care_instruction_ends_registered_translation_run():
    result = parse_label('Composition\nCotton 100%\nCoton\nBaumwolle\nHAND WASH')
    assert result['status'] == 'success', result
    assert result['materials'] == {'cotton': 100}


@pytest.mark.parametrize('text', [
    'Cotton 100%\nCoton\nBaumwolle',
    'Composition\nCotton 100%\nCoton',
    'Composition\nCotton 100%\nCoton\nCoton',
    'Composition\nCotton 100%\nCoton\nSIZE\nBaumwolle',
    'Composition\nCotton 100%\nCoton\nUNKNOWN\nBaumwolle',
    'Composition\nCotton 70%\nCoton\nBaumwolle',
    'Composition\nCotton 100%\nCoton\nLINING\nBaumwolle',
])
def test_translation_run_requires_heading_two_distinct_aliases_and_part_boundary(text):
    assert parse_label(text)['status'] == 'failed'


@pytest.mark.parametrize('prefix', ['SKC#AB1234', 'SKU:AB1234', 'STYLE NO. AB1234'])
def test_product_number_continuation_is_not_a_material_ratio(prefix):
    text = prefix + '\n6686\n09/2025\nComposition\nPolyester 62%\nCotton 38%'
    result = parse_label(text)
    assert result['status'] == 'success', result
    assert result['materials'] == {'polyester': 62, 'cotton': 38}
    info = next(i for i in build_line_infos(text) if i.raw == '6686')
    assert info.is_metadata and not info.numbers and not info.invalid_evidence


@pytest.mark.parametrize('middle,following', [
    ('40', '09/2025'), ('6686%', '09/2025'), ('-6686', '09/2025'),
    ('6686', 'Cotton 100%'), ('6686', '09/2025 UNKNOWN'), ('6686', '14/2025'),
])
def test_product_context_cannot_hide_ratios_or_unconfirmed_number_rows(middle, following):
    infos = build_line_infos('SKC#AB1234\n' + middle + '\n' + following)
    row = next(i for i in infos if i.raw == middle)
    assert not row.is_metadata


@pytest.mark.parametrize('temperature', ['|30|', '|40', '|60|', '|95|'])
def test_wash_outline_after_complete_translation_block_is_metadata(temperature):
    text = 'Composition\nCotton 100%\nCoton\nBaumwolle\n' + temperature + '\nHAND WASH'
    result = parse_label(text)
    assert result['status'] == 'success', result
    assert result['materials'] == {'cotton': 100}


@pytest.mark.parametrize('body,ending', [
    ('Cotton 70%\nCoton\nBaumwolle', '|30|\nHAND WASH'),
    ('Cotton 100%\nCoton\nBaumwolle', '|30|'),
    ('Cotton 100%\nCoton\nBaumwolle', '|30%|\nHAND WASH'),
    ('Cotton 100%\nCoton\nBaumwolle', '|30|\nHAND WASH OLEFIN'),
])
def test_wash_outline_does_not_complete_or_replace_a_fiber_ratio(body, ending):
    assert parse_label('Composition\n' + body + '\n' + ending)['status'] == 'failed'


def test_other_language_with_conflicting_material_ratios_still_fails():
    result = parse_label('Composition\nCotton 100%\nCoton\nBaumwolle\n'
                         'FR: 80% COTON 20% POLYESTER')
    assert result['status'] == 'failed'


def test_incomplete_lining_is_not_borrowed_to_complete_main_composition():
    result = parse_label('OUTER\nCotton 100%\nCoton\nBaumwolle\nLINING\n40%')
    assert result['status'] == 'success', result
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': 100}
    assert 'lining' not in result['parts']
