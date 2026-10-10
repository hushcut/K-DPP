"""A complete original reading must survive an unnecessary or malformed reread."""

from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text
from apps.text import ocr_candidates
from apps.text.ocr_layout import OcrWord


def image_bytes(color='white'):
    stream = BytesIO()
    Image.new('RGB', (200, 200), color).save(stream, format='PNG')
    return stream.getvalue()


def word(text, x, y, direction=0):
    if direction == 90:
        vertices = ((x, y), (x, y + 20), (x - 8, y + 20), (x - 8, y))
    elif direction == -90:
        vertices = ((x, y + 20), (x, y), (x + 8, y), (x + 8, y + 20))
    else:
        vertices = ((x, y), (x + 20, y), (x + 20, y + 8), (x, y + 8))
    xs, ys = zip(*vertices)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices)


def run_payloads(monkeypatch, payloads, extra=False):
    calls = []
    responses = iter(payloads)
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *_args: object())
    monkeypatch.setattr(ocr_text, 'preprocess_image_bytes', lambda _content: image_bytes('gray'))
    def fake_ocr(_client, content, **_kwargs):
        calls.append(content)
        return next(responses)
    monkeypatch.setattr(ocr_text, '_run_google_ocr', fake_ocr)
    result = ocr_text.run_ocr_bytes(image_bytes(), enable_reflection=extra, enable_denoised=extra, enable_rotated=extra)
    return analyze_ocr_result(result), result, calls


READINGS = [
    ('Cotton\n80%\nPolyester\n20%', 'Cotton 80%\nPolyester 20%',
     (word('Cotton', 20, 20), word('80%', 80, 20), word('Polyester', 20, 60), word('20%', 80, 60)),
     {'cotton': 80, 'polyester': 20}, 'Cotton 20% Polyester 80%'),
    ('94% COTTON\n6% SPANDEX', 'COTTON 94%\nSPANDEX 6%',
     (word('94%', 20, 20), word('COTTON', 80, 20), word('6%', 20, 60), word('SPANDEX', 80, 60)),
     {'cotton': 94, 'spandex': 6}, 'Cotton 95% Spandex 5%'),
]


@pytest.mark.parametrize('raw,layout,words,expected,worse', READINGS)
@pytest.mark.parametrize('extra', [False, True])
def test_complete_original_agreement_skips_unnecessary_reread(monkeypatch, raw, layout, words, expected, worse, extra):
    analysis, result, calls = run_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout, layout_words=words), worse], extra)
    assert analysis['status'] == 'success'
    assert analysis['materials'] == expected
    assert result.metadata.confidence == 'medium'
    assert result.metadata.source == 'original'
    assert len(calls) == result.metadata.candidate_count == result.metadata.attempt_count == 1


@pytest.mark.parametrize('defect', ['words', 'transform', 'image', 'variant', 'region'])
@pytest.mark.skipif(not hasattr(ocr_candidates, 'agreed_original_composition'), reason='일치 판정 함수는 수정 후 추가됨')
def test_original_agreement_requires_shared_coordinate_provenance(defect):
    raw, layout, words, _expected, _worse = READINGS[0]
    kwargs = {'image_key': 'same-image', 'image_variant_key': 'same-input',
              'image_transform': (1, 0, 0, 0, 1, 0), 'image_region': (0, 0, 200, 200)}
    if defect == 'words':
        words = ()
    elif defect == 'transform':
        kwargs['image_transform'] = None
    elif defect == 'image':
        kwargs['image_key'] = ''
    elif defect == 'variant':
        kwargs['image_variant_key'] = ''
    else:
        kwargs['image_region'] = ()
    candidates = ocr_text._build_payload_candidates('original', ocr_text.OcrPayload(raw, layout, layout_words=words), **kwargs)
    assert not ocr_candidates.agreed_original_composition(candidates)


@pytest.mark.parametrize('field,value', [('image_variant_key', 'other-input'), ('image_key', 'other-image'), ('image_region', (0,0,100,100))])
@pytest.mark.skipif(not hasattr(ocr_candidates, 'agreed_original_composition'), reason='일치 판정 함수는 수정 후 추가됨')
def test_two_different_coordinate_inputs_are_not_original_agreement(field, value):
    raw, layout, words, _expected, _worse = READINGS[0]
    candidates = ocr_text._build_payload_candidates('original', ocr_text.OcrPayload(raw, layout, layout_words=words),
        image_key='same-image', image_variant_key='same-input', image_transform=(1,0,0,0,1,0), image_region=(0,0,200,200))
    candidates[1] = replace(candidates[1], **{field: value})
    assert not ocr_candidates.agreed_original_composition(candidates)


@pytest.mark.parametrize('with_layout', [False, True])
def test_text_only_medium_result_keeps_existing_reread_guard(monkeypatch, with_layout):
    raw, layout, _words, _expected, worse = READINGS[0]
    payload = ocr_text.OcrPayload(raw, layout if with_layout else '')
    analysis, _result, calls = run_payloads(monkeypatch, [payload, worse])
    assert analysis['status'] == 'failed'
    assert len(calls) == 2
    assert analysis['ocr']['conflicting_parts'] == ['generic']


def test_inferred_percent_markers_do_not_stop_verification(monkeypatch):
    raw, layout, words, _expected, worse = READINGS[0]
    payload = ocr_text.OcrPayload(raw.replace('%', ''), layout.replace('%', ''),
        layout_words=tuple(replace(w, text=w.text.replace('%', '')) for w in words))
    analysis, _result, calls = run_payloads(monkeypatch, [payload, worse])
    assert len(calls) == 2
    assert analysis['status'] == 'failed'
    assert analysis['ocr']['conflicting_parts'] == ['generic']


@pytest.mark.parametrize('extra_row', ['50%', 'OLEFIN 5%', 'POLYESTER', 'UNKNOWN 100%'])
def test_original_agreement_cannot_erase_source_rejections(monkeypatch, extra_row):
    raw, layout, words, _expected, _worse = READINGS[0]
    payload = ocr_text.OcrPayload(raw+'\n'+extra_row, layout+'\n'+extra_row, layout_words=words)
    analysis, _result, _calls = run_payloads(monkeypatch, [payload, layout])
    assert analysis['status'] == 'failed'
    assert analysis['materials'] == {}


@pytest.mark.parametrize('direction', [-90, 90])
def test_rotated_glyphs_without_rotated_rows_remain_unverified(monkeypatch, direction):
    raw = 'POLYESTER 100%\nPOLYESTER 100%'
    layout = 'POLYESTER %\n100\nPOLYESTER %\n100'
    words = tuple(word(text, x, y, direction) for y in [20,80] for text, x in [('POLYESTER',20),('100',60),('%',100)])
    analysis, _result, _calls = run_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout, layout_words=words), 'SIZE M'])
    # Turning individual glyph boxes does not turn their physical baselines.
    assert analysis['status'] == 'failed'
    assert analysis['materials'] == {}


@pytest.mark.parametrize('defect', ['horizontal', 'missing_vertices', 'added_word', 'missing_word', 'changed_ratio', 'missing_numeric_box'])
def test_bad_layout_is_retained_without_direction_and_full_token_proof(monkeypatch, defect):
    raw = 'POLYESTER 100%\nPOLYESTER 100%'
    layout = 'POLYESTER %\n100\nPOLYESTER %\n100'
    words = tuple(word(text, x, y, 90) for y in [20,80] for text, x in [('POLYESTER',20),('100',60),('%',100)])
    if defect == 'horizontal':
        words = tuple(word(w.text, w.left, 20) for w in words)
    elif defect == 'missing_vertices':
        words = tuple(replace(w, vertices=()) for w in words)
    elif defect == 'added_word':
        layout += '\nOLEFIN 5%'
    elif defect == 'missing_word':
        layout = 'POLYESTER %'
    elif defect == 'missing_numeric_box':
        words = tuple(w for w in words if w.text != '100')
    else:
        layout = layout.replace('100', '99', 1)
    analysis, _result, _calls = run_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout, layout_words=words), 'SIZE M'])
    assert analysis['status'] == 'failed'
    assert analysis['materials'] == {}


@pytest.mark.parametrize('direction', [-90, 90])
def test_successful_layout_conflict_survives_vertical_orientation(monkeypatch, direction):
    raw = 'COTTON 80% POLYESTER 20%'
    layout = 'POLYESTER 80% COTTON 20%'
    words = tuple(word(text, x, 20, direction) for text,x in [('COTTON',20),('80%',60),('POLYESTER',100),('20%',140)])
    analysis, result, calls = run_payloads(monkeypatch, [ocr_text.OcrPayload(raw, layout, layout_words=words)])
    assert analysis['status'] == 'failed'
    assert analysis['ocr']['conflicting_parts'] == ['generic']
    assert len(calls) == result.metadata.candidate_count == 1
