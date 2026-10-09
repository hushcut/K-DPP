"""Keep care glyphs, garment sizes and numbered shells outside each other."""
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text.material_extraction import declared_part
from apps.text.ocr_text import OcrMetadata, OcrResult, _assess_candidates, _build_candidate
from apps.text.parse_label import build_line_infos, parse_label, parse_parts


@pytest.mark.parametrize('glyph', ['(300', '( 300', '(300)', '(400'])
@pytest.mark.parametrize('alternating', [False, True])
def test_parenthesized_wash_outline_after_confirmed_composition(glyph, alternating):
    text = '겉감\n레이온 68%\n폴리에스터 27%\n폴리우레탄 5%'
    if alternating:
        text = text.replace(' 68', '\n68').replace(' 27', '\n27').replace(' 5', '\n5')
    result = parse_label(text + '\n' + glyph)
    assert result['status'] == 'success'
    assert result['materials'] == {'rayon': 68, 'polyester': 27, 'polyurethane': 5}
    assert result['parse_evidence']['observed_ratios'] == {'outer': [68, 27, 5]}


@pytest.mark.parametrize('text', [
    'Cotton 70%\n(300', 'Cotton 100%\nCOMPOSITION\n(300',
    'Cotton 100%\n300%', 'Cotton 100%\n(300%',
    'Cotton 100%\nCotton (300', 'Cotton 100%\n30%\n(300',
    'Cotton 100%\nOLEFIN 5%\n(300', 'Cotton 100%\nPolyester\n(300',
])
def test_wash_outline_cannot_hide_unconfirmed_material_or_ratio(text):
    assert parse_label(text)['status'] == 'failed'


def test_unadorned_large_number_is_not_classified_as_a_wash_glyph():
    row = build_line_infos('Cotton 100%\n300')[-1]
    assert row.invalid_evidence
    assert not row.is_metadata


@pytest.mark.parametrize('text', [
    '1\nMade in Korea\nBrand\n100 면',
    'Made in Korea\nBrand\n1\n100 면',
    '2\nMade in Korea\nBrand\nCotton 100%',
])
def test_leading_header_size_is_not_an_orphan_ratio(text):
    result = parse_label(text)
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 100}
    assert 'unlabeled_garment_size_inferred' in result['warnings']
    if '%' not in text:
        assert 'generic:ratio_marker_inferred' in result['warnings']
    assert result['confidence']['parser'] == 'medium'
    assert result['parse_evidence']['observed_ratios'] == {'generic': [100]}


@pytest.mark.parametrize('text', [
    '1%\nMade in Korea\nCotton 100%', '1\nCotton 100%',
    '1\nMade in Korea\nCotton 99%', '1\nMade in Korea\nCOMPOSITION\nCotton 100%',
    'Made in Korea\nCOMPOSITION\n1\nCotton 100%',
    'Cotton 100%\n1\nMade in Korea', '1\n2\nMade in Korea\nCotton 100%',
    '1\nMade in Korea\nCotton 100%\nOLEFIN 1%',
])
def test_header_size_inference_keeps_actual_ratio_evidence(text):
    assert parse_label(text)['status'] == 'failed'


@pytest.mark.parametrize('heading', ['신체치수', '가슴 둘레', '허리둘레'])
@pytest.mark.parametrize('inline', [False, True])
def test_explicit_body_measurement_does_not_block_composition(heading, inline):
    header = f'{heading}: 108' if inline else f'{heading}\n108'
    result = parse_label(header + '\n면 100%')
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 100}


@pytest.mark.parametrize('header', ['신체치수\n108%', '가슴둘레 OLEFIN 10%', '허리둘레\nPolyester 5%'])
def test_measurement_header_does_not_erase_fiber_or_percent(header):
    assert parse_label('Cotton 100%\n' + header)['status'] == 'failed'


@pytest.mark.parametrize('header', ['신체치수', '가슴둘레', '허리둘레'])
@pytest.mark.parametrize('ratio', [20, 108])
def test_inline_measurement_percent_cannot_hide_a_ratio(header, ratio):
    assert parse_label(f'Cotton 100%\n{header}: {ratio}%')['status'] == 'failed'


@pytest.mark.parametrize('first,second', [
    ('OUTSHELL', 'OUTSHELL2'), ('OUTSHELL1', 'OUTSHELL2'),
    ('CUTSHELL', 'OUTSHELL2'), ('겉감1', '겉감2'),
    ('겉감 1', '겉감 2'), ('OUTER 1', 'OUTER 2'),
])
def test_numbered_outer_fabrics_keep_separate_compositions(first, second):
    text = f'{first} Cotton 100%\n{second} Cotton 70% Polyester 30%'
    result = parse_label(text)
    assert result['status'] == 'failed'
    assert result['error_code'] == 'ambiguous_composition'
    assert result['materials'] == result['parts'] == {}
    assert parse_parts(text) == {'outer': {'cotton': 100}, 'outer_2': {'cotton': 70, 'polyester': 30}}


@pytest.mark.parametrize('first,second', [('OUTSHELL1', 'OUTSHELL2'), ('겉감1', '겉감2')])
def test_numbered_heading_indices_are_not_plain_ratios(first, second):
    text = f'{first} Cotton 100\n{second} Cotton 70 Polyester 30'
    result = parse_label(text)
    assert result['status'] == 'failed'
    assert result['error_code'] == 'ambiguous_composition'
    assert result['parts'] == {}
    assert parse_parts(text) == {'outer': {'cotton': 100}, 'outer_2': {'cotton': 70, 'polyester': 30}}


@pytest.mark.parametrize('first', ['OUTSHELL Cotton', 'OUTSHELL Cotton 70%', '겉감1 UNKNOWN 100%'])
def test_second_outer_cannot_substitute_an_unconfirmed_primary(first):
    result = parse_label(first + '\nOUTSHELL2 Polyester 100%')
    assert result['status'] == 'failed'
    assert result['materials'] == {}


def test_conflicting_secondary_fabric_blocks_representative_outer():
    text = 'OUTSHELL Cotton 100%\nOUTSHELL2 Cotton 70% Polyester 30%\nOUTSHELL2 Nylon 100%'
    result = parse_label(text)
    assert result['status'] == 'failed'
    assert result['materials'] == result['parts'] == {}
    assert parse_parts(text) == {'outer': {'cotton': 100}}
    assert 'outer_2:ambiguous_composition_candidates' in result['warnings']


def test_candidate_assessment_and_response_keep_numbered_parts():
    text = 'OUTSHELL Cotton 100%\nOUTSHELL2 Cotton 70% Polyester 30%'
    candidates = [_build_candidate('original', text), _build_candidate('preprocessed', text)]
    decision = _assess_candidates(candidates)
    assert decision.status == 'failed'
    metadata = OcrMetadata('original', 'high', 2, 'JPEG', 100, 100,
                           conflicting_parts=decision.conflicting_parts,
                           unpaired_ratio_parts=decision.unpaired_ratio_parts,
                           rejected_composition_parts=decision.rejected_composition_parts)
    response = analyze_ocr_result(OcrResult(decision.best.text, metadata))
    assert response['status'] == 'failed'
    assert response['materials'] == response['parts'] == {}
    assert response['parse_evidence']['paired_material_ratios']['outer_2'] == [['cotton', 70.0], ['polyester', 30.0]]
    assert parse_parts(text)['outer_2'] == {'cotton': 70, 'polyester': 30}


def test_unconfirmed_secondary_outer_blocks_representative_and_preserves_warning():
    text = 'OUTSHELL Cotton 100%\nOUTSHELL2 Polyester'
    decision = _assess_candidates([_build_candidate('original', text)])
    assert decision.status == 'failed'
    assert decision.rejected_composition_parts == {'outer_2': ('unpaired_material_rows',)}


def test_missing_primary_ratio_does_not_make_distinct_numbered_parts_representative():
    raw = 'OUTSHELL Cotton\nOUTSHELL2 Polyester 100%'
    complete = 'OUTSHELL Cotton 100%\nOUTSHELL2 Polyester 100%'
    decision = _assess_candidates([_build_candidate('original', raw), _build_candidate('layout', complete, layout_used=True)])
    assert decision.status == 'failed'
    assert 'outer' in decision.rejected_composition_parts
    assert parse_parts(complete) == {'outer': {'cotton': 100}, 'outer_2': {'polyester': 100}}


@pytest.mark.parametrize('heading', ['OUTSHELL20', 'CUTSHELL20', '겉감20', 'OUTSHELL2X'])
def test_second_outer_marker_does_not_match_longer_identifier(heading):
    assert declared_part(heading) is None


@pytest.mark.parametrize('heading,ratio', [('OUTSHELL', 1), ('OUTSHELL', 2), ('겉감', 2)])
def test_percentage_after_heading_is_not_a_fabric_index(heading, ratio):
    result = parse_label(f'{heading} {ratio}% Cotton {100 - ratio}% Polyester')
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': ratio, 'polyester': 100 - ratio}
