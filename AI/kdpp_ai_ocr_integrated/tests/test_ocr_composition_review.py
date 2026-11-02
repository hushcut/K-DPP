"""Explicit review confirms displayed values; automatic evidence stays intact."""

from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_ocr_result, get_ocr_review_options
from apps.text import ocr_text
from apps.text.ocr_layout import OcrWord


TEXT = 'MATERIAL\nCOTTON 80%\nNYLON 20%\nCUSTOMFIBER 60%\nPOLYESTER 40%'


def result_for(text=TEXT, *, image_key='a' * 64, best_text='UNREAD 100%'):
    original = replace(ocr_text._build_candidate('original', text),
                       image_key=image_key, image_variant_key='b' * 64)
    return ocr_text.OcrResult(best_text, ocr_text.OcrMetadata(
        source='material_crop_rotated', confidence='low', candidate_count=4,
        image_format='JPEG', width=800, height=1200,
        conflicting_parts=('generic',), unpaired_ratio_parts=('generic',),
        rejected_composition_parts={'generic': ('unresolved_material_token',)},
        warnings=('expanded_candidate_used',),
    ), original_candidate=original)


def test_preview_and_confirmation_leave_the_automatic_failure_unchanged():
    source = result_for()
    automatic = analyze_ocr_result(source)
    assert automatic['status'] == 'failed'
    options = get_ocr_review_options(source)
    assert len(options) == 1
    option = options[0]
    assert option['materials'] == {'cotton': 80, 'nylon': 20}
    assert option['confirmation_required'] is True
    assert option['confirmation_scope'] == 'materials_and_ratios'
    assert 'confirmed_representative_selection:first_generic' not in option['warnings']
    reviewed = analyze_ocr_result(source, confirmed_review_id=option['id'])
    assert reviewed['status'] == 'success'
    assert reviewed['materials'] == option['materials']
    assert reviewed['selected_part'] == 'generic'
    assert reviewed['ocr'] == automatic['ocr']
    assert reviewed['confidence'] == {'ocr': 'low', 'parser': 'medium'}
    evidence = reviewed['parse_evidence']
    assert 'generic_secondary' in evidence['rejected_composition_parts']
    assert evidence['review']['automatic_status'] == 'failed'
    assert evidence['review']['automatic_warnings'] == automatic['warnings']
    assert evidence['review']['source'] == 'original'
    assert 'manual_composition_review_confirmed:first_generic' in reviewed['warnings']
    assert 'automatic_composition_not_confirmed' in reviewed['warnings']
    assert analyze_ocr_result(source) == automatic


@pytest.mark.parametrize('value', ['', True, False, 0, 1, [], {}])
def test_confirmation_id_is_not_a_truthy_flag(value):
    with pytest.raises(ValueError):
        analyze_ocr_result(result_for(), confirmed_review_id=value)


@pytest.mark.parametrize('change', ['photo', 'reading', 'variant'])
def test_confirmation_cannot_be_reused_for_another_photo_or_reading(change):
    source = result_for()
    choice = get_ocr_review_options(source)[0]['id']
    candidate = source.original_candidate
    if change == 'photo':
        candidate = replace(candidate, image_key='c' * 64)
    elif change == 'reading':
        candidate = replace(candidate, text=TEXT.replace('80%', '75%').replace('20%', '25%'))
    else:
        candidate = replace(candidate, image_variant_key='d' * 64)
    with pytest.raises(ValueError):
        analyze_ocr_result(replace(source, original_candidate=candidate), confirmed_review_id=choice)


@pytest.mark.parametrize('text', [
    'MATERIAL\nCOTTON 80%\nNYLON 19%\nPOLYESTER 100%',
    'MATERIAL\nCUSTOMFIBER 20%\nCOTTON 80%\nPOLYESTER 100%',
    'MATERIAL\nCOTTON -80%\nNYLON 20%\nPOLYESTER 100%',
    'MATERIAL\nCOTTON 100%\n5%',
    'MATERIAL\nCOTTON 100%\nCUSTOMFIBER 5%',
    'OUTER COTTON 100%\nLINING POLYESTER 100%',
    'COTTON 100%',
])
def test_review_cannot_repair_selected_numbers_names_or_explicit_parts(text):
    source = result_for(text)
    assert get_ocr_review_options(source) == []
    with pytest.raises(ValueError):
        analyze_ocr_result(source, confirmed_review_id='first_generic:unavailable')


@pytest.mark.parametrize('change', ['missing', 'crop', 'layout', 'identity'])
def test_only_the_identified_original_response_supplies_review_options(change):
    source = result_for()
    candidate = source.original_candidate
    candidate = (None if change == 'missing' else replace(candidate, **{
        'crop': {'source': 'material_crop'},
        'layout': {'layout_used': True},
        'identity': {'image_key': ''},
    }[change]))
    assert get_ocr_review_options(replace(source, original_candidate=candidate)) == []


def test_mutating_preview_or_review_response_does_not_change_stored_evidence():
    source = result_for()
    option = get_ocr_review_options(source)[0]
    option['materials']['cotton'] = 1
    reviewed = analyze_ocr_result(source, confirmed_review_id=option['id'])
    assert reviewed['materials'] == {'cotton': 80, 'nylon': 20}
    reviewed['ocr']['rejected_composition_parts']['generic'].append('changed')
    assert source.metadata.rejected_composition_parts == {'generic': ('unresolved_material_token',)}


def test_normal_ocr_pipeline_preserves_original_for_review_without_more_calls(monkeypatch):
    buffer = BytesIO()
    Image.new('RGB', (800, 1200), 'white').save(buffer, format='PNG')
    calls = []

    def detect(*_args, **_kwargs):
        calls.append(True)
        text = TEXT if len(calls) == 1 else 'NYLON 100%'
        return ocr_text.OcrPayload(text=text, layout_words=(
            OcrWord('MATERIAL', 10, 10, 100, 30),
        ))

    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *_a, **_k: object())
    monkeypatch.setattr(ocr_text, '_run_google_ocr', detect)
    source = ocr_text.run_ocr_bytes(buffer.getvalue(), enable_reflection=False,
        enable_denoised=False, enable_rotated=False, enable_material_region=False)
    assert source.original_candidate.text == TEXT
    assert source.metadata.source == 'preprocessed'
    count = len(calls)
    option = get_ocr_review_options(source)[0]
    assert analyze_ocr_result(source, confirmed_review_id=option['id'])['materials'] == {'cotton': 80, 'nylon': 20}
    assert len(calls) == count
    assert 'original_candidate=' not in repr(source)
