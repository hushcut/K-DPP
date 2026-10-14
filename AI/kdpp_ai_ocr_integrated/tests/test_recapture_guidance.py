"""Recapture advice must not erase uncertainty or blame incomplete OCR on a photo."""
from dataclasses import replace

import pytest

from apps.service.label_analysis import analyze_label_text, analyze_ocr_result, get_ocr_review_options
from apps.service.response_contract import LabelResponseContract
from apps.text.ocr_text import OcrAttempt, OcrMetadata, OcrResult, _build_candidate


def reading(text):
    candidate = replace(_build_candidate('original', text), image_key='a' * 64,
                        image_variant_key='b' * 64)
    return OcrResult(text, OcrMetadata(
        source='original', confidence='medium', candidate_count=1,
        image_format='JPEG', width=800, height=1200,
        attempts=(OcrAttempt('original', 'success', 0, False),), attempt_count=1,
    ), original_candidate=candidate)


@pytest.mark.parametrize('text,reason', [
    ('QUALITY LABEL\nMADE IN VIETNAM', 'composition_text_missing'),
    ('COMPOSITION\n100%\n70%\nPOLYESTER 90%', 'composition_incomplete'),
    ('OUTER\nCOTTON 70%', 'composition_incomplete'),
    ('COMPOSITION\nUNKNOWN 100%', 'composition_incomplete'),
])
def test_recapture_preserves_failure_and_all_existing_fields(text, reason):
    source = reading(text)
    baseline = analyze_ocr_result(replace(source, metadata=replace(source.metadata, attempts=())))
    result = analyze_ocr_result(source)
    assert result['status'] == 'failed'
    assert result['materials'] == result['parts'] == {}
    assert result['selected_part'] == ''
    assert result['parse_evidence']['recapture'] == {
        'action': 'retake_composition_region', 'reason': reason, 'basis': 'current_ocr'}
    for key in baseline:
        if key not in {'ocr', 'parse_evidence'}:
            assert result[key] == baseline[key]
    assert {k: v for k, v in result['parse_evidence'].items() if k != 'recapture'} == baseline['parse_evidence']
    LabelResponseContract.model_validate(result)
    result['parse_evidence']['recapture']['reason'] = 'changed'
    assert analyze_ocr_result(source)['parse_evidence']['recapture']['reason'] == reason


@pytest.mark.parametrize('outcome,code', [
    ('failed', 'service_error'), ('failed', 'timeout'), ('failed', 'quota_exceeded'),
    ('failed', 'cache_miss'), ('skipped', 'total_timeout'), ('skipped', ''),
    ('failed', 'unknown'), ('success', 'service_error'),
])
def test_failed_or_incomplete_attempts_do_not_imply_a_bad_photo(outcome, code):
    source = reading('COMPOSITION\n100%\n70%\nPOLYESTER 90%')
    source = replace(source, metadata=replace(source.metadata, attempts=(
        *source.metadata.attempts, OcrAttempt('preprocessed', outcome, 0, False, code))))
    result = analyze_ocr_result(source)
    assert result['status'] == 'failed'
    assert 'recapture' not in result['parse_evidence']


@pytest.mark.parametrize('change', [
    {'attempts': ()}, {'attempt_failures': ('preprocessed:service_error',)},
    {'conflicting_parts': ('generic',)},
])
def test_missing_attempt_history_and_conflicts_do_not_recommend_recapture(change):
    source = reading('UNKNOWN 100%')
    result = analyze_ocr_result(replace(source, metadata=replace(source.metadata, **change)))
    assert 'recapture' not in result['parse_evidence']


def test_manual_review_takes_priority_over_recapture():
    source = reading('MATERIAL\nRAYON 45%\nNYLON 28%\nPOLYESTER 22%\nPOLYURETHANE 5%\nCUSTOMFIBER 60%\nPOLYESTER 40%')
    result = analyze_ocr_result(source)
    option = get_ocr_review_options(source)[0]
    assert result['status'] == 'failed'
    assert result['parse_evidence']['review']['available']
    assert 'recapture' not in result['parse_evidence']
    confirmed = analyze_ocr_result(source, confirmed_review_id=option['id'])
    assert confirmed['status'] == 'success'
    assert 'recapture' not in confirmed['parse_evidence']


@pytest.mark.parametrize('text', ['COTTON 100%', 'OUTER COTTON 100%'])
def test_success_does_not_gain_a_recapture_instruction(text):
    result = analyze_ocr_result(reading(text))
    assert result['status'] == 'success'
    assert 'recapture' not in result['parse_evidence']


def test_text_only_failure_cannot_assess_photo_acquisition():
    assert 'recapture' not in analyze_label_text('UNKNOWN 100%')['parse_evidence']
