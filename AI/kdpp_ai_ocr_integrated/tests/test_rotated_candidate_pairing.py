"""Rotated geometry must verify the pairs before discarding failed evidence."""

from dataclasses import replace
from io import BytesIO
from math import cos, radians, sin, tan

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text
from apps.text.ocr_layout import OcrWord, spatial_text_from_words


def polygon(text, cx, cy, width, angle=0, direction=90, scale=1, page=0):
    theta = radians(angle)
    points = []
    for x, y in ((-width / 2, -6), (width / 2, -6), (width / 2, 6), (-width / 2, 6)):
        px = round((cx + x * cos(theta) - y * sin(theta) + 2000) * scale)
        py = round((cy + x * sin(theta) + y * cos(theta) + 2000) * scale)
        points.append((4000 * scale - py, px) if direction == 90 else (py, 4000 * scale - px))
    xs, ys = zip(*points)
    return OcrWord(text, min(xs), min(ys), max(xs), max(ys), tuple(points), page)


def composition_words(angle=0, direction=90, scale=1):
    shift = 400 * tan(radians(angle))
    return (
        polygon('COTTON', 120, 160, 100, angle, direction, scale),
        polygon('80%', 520, 160 + shift, 48, angle, direction, scale),
        polygon('POLYESTER', 120, 205, 140, angle, direction, scale),
        polygon('20%', 520, 205 + shift, 48, angle, direction, scale),
    )


def payload(raw, words):
    return ocr_text.OcrPayload(raw, spatial_text_from_words(list(words)), layout_words=tuple(words))


def image_bytes(color='white'):
    stream = BytesIO()
    Image.new('RGB', (500, 500), color).save(stream, format='PNG')
    return stream.getvalue()


def analysis(monkeypatch, candidate):
    calls = []
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *_args: object())
    monkeypatch.setattr(ocr_text, '_resolve_credential_path', lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, 'preprocess_image_bytes', lambda _content: image_bytes('gray'))
    def fake_ocr(_client, content, **_kwargs):
        calls.append(content)
        return candidate
    monkeypatch.setattr(ocr_text, '_run_google_ocr', fake_ocr)
    result = ocr_text.run_ocr_bytes(
        image_bytes(), enable_reflection=False, enable_denoised=False,
        enable_rotated=False, enable_material_region=False,
    )
    return analyze_ocr_result(result), result, calls


@pytest.mark.parametrize('angle,ratio_y,poly_y,second_y,ratio_x', [
    (18, 186, 186, 160, 200), (2, 174, 174, 160, 520),
])
@pytest.mark.parametrize('raw', [
    'COTTON\n20%\n80%\nPOLYESTER\nWASHING\nSTORAGE',
    'COTTON 20%\nPOLYESTER 80%\nWASHING\nSTORAGE',
])
def test_opposing_fold_cannot_confirm_swapped_percentages(
    monkeypatch, angle, ratio_y, poly_y, second_y, ratio_x, raw,
):
    words = (
        polygon('COTTON', 120, 160, 100, angle),
        polygon('80%', ratio_x, ratio_y, 36, angle),
        polygon('POLYESTER', 120, poly_y, 120, -angle),
        polygon('20%', ratio_x, second_y, 36, -angle),
        polygon('WASHING', 100, 450, 100),
        polygon('STORAGE', 100, 500, 100),
    )
    candidate = payload(raw, words)
    candidates = ocr_text._build_payload_candidates('original', candidate)
    assert any(c.layout_used and c.text == candidate.layout_text for c in candidates)
    parsed, _result, _calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'failed'
    assert parsed['materials'] == {}


@pytest.mark.parametrize('direction', [-90, 90])
@pytest.mark.parametrize('angle', [-6, -2, 0, 2, 6])
def test_uniform_rotated_polygons_expose_swapped_direct_raw(monkeypatch, angle, direction):
    candidate = payload('COTTON 20%\nPOLYESTER 80%', composition_words(angle, direction))
    parsed, _result, _calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'failed'
    assert parsed['materials'] == {}
    assert parsed['ocr']['conflicting_parts'] == ['generic']


@pytest.mark.parametrize('direction', [-90, 90])
@pytest.mark.parametrize('angle', [-6, -2, 0, 2, 6])
@pytest.mark.parametrize('scale', [1, 3])
def test_uniform_rotation_requires_and_preserves_matching_direct_pairs(monkeypatch, angle, direction, scale):
    candidate = payload('COTTON 80%\nPOLYESTER 20%', composition_words(angle, direction, scale))
    parsed, result, calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'success'
    assert parsed['materials'] == {'cotton': 80, 'polyester': 20}
    assert len(calls) == result.metadata.candidate_count == 1


@pytest.mark.parametrize('raw', ['COTTON\n80%\nPOLYESTER\n20%', 'COTTON 80\nPOLYESTER 20',
                               'COTTON POLYESTER 80% 20%'])
def test_inferred_row_or_percent_pairing_does_not_discard_failed_layout(raw):
    candidate = payload(raw, composition_words())
    if '%' not in raw:
        candidate = replace(candidate, layout_text=candidate.layout_text.replace('%', ''),
                            layout_words=tuple(replace(w, text=w.text.replace('%', '')) for w in candidate.layout_words))
    candidates = ocr_text._build_payload_candidates('original', candidate)
    assert any(c.layout_used and c.text == candidate.layout_text for c in candidates)


@pytest.mark.parametrize('defect', ['opposite_direction', 'opposite_residual', 'horizontal_number',
                                  'missing_number_polygon', 'degenerate_polygon', 'second_page'])
def test_partial_or_mixed_polygon_evidence_keeps_failed_layout(defect):
    words = list(composition_words(2))
    if defect == 'opposite_direction':
        words[1] = polygon('80%', 520, 174, 48, 2, -90)
    elif defect == 'opposite_residual':
        words[1] = polygon('80%', 520, 174, 48, -2)
    elif defect == 'horizontal_number':
        words[1] = replace(words[1], vertices=((20, 20), (68, 20), (68, 32), (20, 32)))
    elif defect == 'missing_number_polygon':
        words[1] = replace(words[1], vertices=())
    elif defect == 'degenerate_polygon':
        words[1] = replace(words[1], vertices=((20, 20),) * 4)
    else:
        words[1] = replace(words[1], page=1)
    candidate = payload('COTTON 80%\nPOLYESTER 20%', words)
    candidates = ocr_text._build_payload_candidates('original', candidate)
    assert any(c.layout_used and c.text == candidate.layout_text for c in candidates)


@pytest.mark.parametrize('reason', ['unresolved_material_token', 'invalid_composition_evidence', 'invalid_ratio'])
def test_rotated_exception_never_discards_independent_rejection(monkeypatch, reason):
    candidate = payload('COTTON 80%\nPOLYESTER 20%', composition_words())
    original_build = ocr_text._build_candidate
    def rejected_layout(source, text, *, layout_used=False):
        parsed = original_build(source, text, layout_used=layout_used)
        if text == candidate.layout_text:
            return replace(parsed, parser_status='failed', rejected_composition_parts={'generic': (reason,)})
        return parsed
    monkeypatch.setattr(ocr_text, '_build_candidate', rejected_layout)
    candidates = ocr_text._build_payload_candidates('original', candidate)
    assert any(reason in c.rejected_composition_parts.get('generic', ()) for c in candidates)


@pytest.mark.parametrize('direction', [-90, 90])
def test_single_fiber_actual_rotation_preserves_direct_100_percent(monkeypatch, direction):
    words = (
        polygon('POLYESTER', 120, 160, 140, direction=direction),
        polygon('100%', 520, 160, 48, direction=direction),
        polygon('POLYESTER', 120, 205, 140, direction=direction),
        polygon('100%', 520, 205, 48, direction=direction),
    )
    candidate = payload('POLYESTER 100%\nPOLYESTER 100%', words)
    parsed, result, calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'success'
    assert parsed['materials'] == {'polyester': 100}
    assert len(calls) == result.metadata.candidate_count == 1


@pytest.mark.parametrize('direction', [-90, 90])
def test_repeated_100_percent_cannot_erase_unproved_upright_rows(monkeypatch, direction):
    words = []
    for y in (20, 80):
        for text, x in (('POLYESTER', 20), ('100', 60), ('%', 100)):
            if direction == 90:
                vertices = ((x, y), (x, y + 20), (x - 8, y + 20), (x - 8, y))
            else:
                vertices = ((x, y + 20), (x, y), (x + 8, y), (x + 8, y + 20))
            xs, ys = zip(*vertices)
            words.append(OcrWord(text, min(xs), min(ys), max(xs), max(ys), vertices))
    candidate = ocr_text.OcrPayload(
        'POLYESTER 100%\nPOLYESTER 100%',
        'POLYESTER %\n100\nPOLYESTER %\n100', layout_words=tuple(words),
    )
    parsed, _result, _calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'failed'
    assert parsed['materials'] == {}


def test_visible_unknown_in_failed_layout_survives_matching_upright_reading(monkeypatch):
    words = (
        polygon('POLYESTER', 120, 160, 140), polygon('100%', 520, 160, 48),
        polygon('MADE', 120, 260, 60), polygon('IN', 220, 260, 24), polygon('FAUX', 320, 260, 60),
    )
    candidate = ocr_text.OcrPayload(
        'POLYESTER 100%\nMADE IN FAUX', 'FAUX 100%\nPOLYESTER\nMADE IN', layout_words=words,
    )
    candidates = ocr_text._build_payload_candidates('original', candidate)
    assert any('unresolved_material_token' in c.rejected_composition_parts.get('generic', ()) for c in candidates)
    parsed, _result, _calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'failed'
    assert parsed['materials'] == {}


def test_close_rotated_rows_do_not_add_a_guessed_column_pairing(monkeypatch):
    words = (
        polygon('COTTON', 120, 160, 100), polygon('80%', 520, 160, 48),
        polygon('POLYESTER', 120, 164, 140), polygon('20%', 520, 164, 48),
    )
    candidate = payload('COTTON 20%\nPOLYESTER 80%', words)
    candidates = ocr_text._build_payload_candidates('original', candidate)
    assert not any(c.text == 'POLYESTER COTTON 80% 20%' for c in candidates)
    parsed, _result, _calls = analysis(monkeypatch, candidate)
    assert parsed['status'] == 'failed'
    assert parsed['materials'] == {}
