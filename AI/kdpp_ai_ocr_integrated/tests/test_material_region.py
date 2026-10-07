from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from apps.text.ocr_cache import OcrTextCache, image_sha256
from apps.text.ocr_errors import InvalidImageError, OcrUnavailableError
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import find_material_region, prepare_material_region
from apps.text import ocr_text
from apps.text.ocr_text import OcrPayload, _build_payload_candidates, run_ocr_bytes
from apps.text.parse_label import parse_label


def image_bytes(size=(800, 600), exif_orientation=1):
    image = Image.new('RGB', size, 'white')
    ImageDraw.Draw(image).rectangle((150, 250, 170, 270), fill='black')
    buffer = BytesIO()
    exif = image.getexif()
    exif[274] = exif_orientation
    image.save(buffer, format='JPEG', exif=exif)
    return buffer.getvalue()


def composition_words(ratio='5%', material='Polyester'):
    return tuple(word for name, value, y in [(material, ratio, 240), ('Rayon', '21%', 280), ('Span', '4%', 320)]
                 for word in [OcrWord(name, 100, y, 220, y+20), OcrWord(value, 350, y, 400, y+20)])


def located_candidates(words):
    text = '\n'.join(word.text for word in words)
    return _build_payload_candidates('original', OcrPayload(text, layout_words=words),
                                    image_key='image', image_variant_key='original',
                                    image_transform=(1, 0, 0, 0, 1, 0), image_region=(0, 0, 800, 600))


def test_region_keeps_complete_rows_and_is_independent_of_candidate_order():
    words = composition_words() + (OcrWord('OUTER', 60, 205, 170, 225), OcrWord('MADE', 100, 550, 220, 570))
    candidates = located_candidates(words)
    region = find_material_region(candidates, 800, 600)
    assert region is not None
    left, top, right, bottom = region
    for word in words[:-1]:
        assert left <= word.left < word.right <= right
        assert top <= word.top < word.bottom <= bottom
    assert bottom < words[-1].top
    assert find_material_region(candidates + candidates, 800, 600) == region
    assert find_material_region(list(reversed(candidates)), 800, 600) == region


@pytest.mark.parametrize('label', ['POLY 100%', 'KAY:1100%', 'Adorable 40%'])
def test_unknown_percentage_rows_can_be_located_without_becoming_valid_materials(label):
    words = (OcrWord(label, 100, 240, 400, 260),)
    assert find_material_region(located_candidates(words), 800, 600) is not None
    assert parse_label(label)['status'] == 'failed'


@pytest.mark.parametrize('failure', ['no_words', 'no_frame', 'no_variant', 'no_ratio', 'no_material',
                                      'shrinkage', 'page', 'out_of_bounds', 'distant', 'thumbnail'])
def test_region_requires_local_material_ratio_and_verified_coordinates(failure):
    words = composition_words()
    if failure == 'no_words':
        words = ()
    elif failure == 'no_ratio':
        words = tuple(w for w in words if '%' not in w.text)
    elif failure == 'no_material':
        words = tuple(w for w in words if '%' in w.text)
    elif failure == 'shrinkage':
        words = (words[0], OcrWord('shrinkage', 100, 280, 240, 300), OcrWord('5%', 350, 280, 400, 300))
    elif failure == 'page':
        words = tuple(replace(w, page=1) for w in words)
    elif failure == 'out_of_bounds':
        words = tuple(replace(w, left=-1) for w in words)
    elif failure == 'distant':
        words = (words[0], OcrWord('5%', 350, 550, 400, 570))
    candidates = located_candidates(words)
    if failure == 'no_frame':
        candidates = [replace(c, image_region=()) for c in candidates]
    elif failure == 'no_variant':
        candidates = [replace(c, image_variant_key='') for c in candidates]
    size = (200, 200) if failure == 'thumbnail' else (800, 600)
    assert find_material_region(candidates, *size) is None


@pytest.mark.parametrize('rotated', [False, True])
def test_crop_inverse_coordinates_match_actual_enhanced_pixels(rotated):
    content = image_bytes()
    region = (60, 190, 440, 390)
    cropped = prepare_material_region(content, region, rotated=rotated)
    with Image.open(BytesIO(cropped.content)) as image:
        assert image.width >= 1799
        assert image.width * image.height <= 16_000_000
        bbox = image.convert('L').point(lambda value: 255 if value < 80 else 0).getbbox()
    x, y = (bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2
    a, b, c, d, e, f = cropped.transform
    assert a*x + b*y + c == pytest.approx(160, abs=2)
    assert d*x + e*y + f == pytest.approx(260, abs=2)
    assert cropped.region == region


@pytest.mark.parametrize('box', [(-1, 0, 400, 400), (0, 0, 801, 400), (0, 0, 400, 601),
                               (400, 0, 400, 400), (0, 0, 400.0, 400), (0, 0, 400)])
def test_invalid_region_is_rejected(box):
    with pytest.raises(InvalidImageError):
        prepare_material_region(image_bytes(), box)


def test_unmapped_exif_orientation_is_not_cropped():
    with pytest.raises(InvalidImageError):
        prepare_material_region(image_bytes(exif_orientation=6), (60, 190, 440, 390))


def words_in_crop(words, transform):
    a, b, c, d, e, f = transform
    determinant = a*e-b*d
    mapped = []
    for word in words:
        vertices = tuple((round((e*(x-c)-b*(y-f))/determinant), round((-d*(x-c)+a*(y-f))/determinant))
                         for x, y in [(word.left, word.top), (word.right, word.top),
                                      (word.right, word.bottom), (word.left, word.bottom)])
        mapped.append(replace(word, left=min(x for x, y in vertices), top=min(y for x, y in vertices),
                              right=max(x for x, y in vertices), bottom=max(y for x, y in vertices), vertices=vertices))
    return tuple(mapped)


def reread_fixture(monkeypatch, ratio='5%', material='Polyester', extra=False):
    content = image_bytes()
    raw_words = composition_words(ratio, material)
    raw = f'{material} {ratio}\nRayon 21%\nSpan 4%'
    if extra:
        raw_words += (OcrWord('10%', 350, 500, 400, 520),)
        raw += '\n10%'
    region = find_material_region(located_candidates(raw_words), 800, 600)
    assert region is not None
    crop = prepare_material_region(content, region)
    rotated = prepare_material_region(content, region, rotated=True, enhancement='adaptive_mild')
    preprocessed = ocr_text.preprocess_image_bytes(content)
    with Image.open(BytesIO(preprocessed)) as image:
        sx, sy = image.width/800, image.height/600
    processed_words = tuple(replace(w, left=round(w.left*sx), right=round(w.right*sx), top=round(w.top*sy), bottom=round(w.bottom*sy)) for w in raw_words)
    corrected = 'Polyester 75%\nRayon 21%\nSpan 4%'
    payloads = {content: ('original', OcrPayload(raw, layout_words=raw_words)),
                preprocessed: ('preprocessed', OcrPayload(raw, layout_words=processed_words)),
                crop.content: (crop.source, OcrPayload(corrected, layout_words=words_in_crop(composition_words('75%'), crop.transform))),
                rotated.content: (rotated.source, OcrPayload(corrected, layout_words=words_in_crop(composition_words('75%'), rotated.transform)))}
    calls = []
    def provider(client, candidate_content, **kwargs):
        source, payload = payloads[candidate_content]
        calls.append(source)
        return payload
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *args: object())
    monkeypatch.setattr(ocr_text, '_run_google_ocr', provider)
    monkeypatch.setattr(ocr_text, '_resolve_credential_path', lambda *args: (None, None))
    monkeypatch.delenv('KDPP_ENABLE_MATERIAL_REGION_OCR', raising=False)
    return content, payloads, calls


def parsed(result):
    return parse_label(result.text, conflicting_parts=result.metadata.conflicting_parts,
                       unpaired_ratio_parts=result.metadata.unpaired_ratio_parts,
                       rejected_composition_parts=result.metadata.rejected_composition_parts)


def test_default_reread_recovers_missing_digit_and_stops_after_success(monkeypatch):
    content, _payloads, calls = reread_fixture(monkeypatch)
    result = run_ocr_bytes(content)
    assert calls == ['original', 'preprocessed', 'material_crop']
    assert result.metadata.candidate_count == 3
    assert result.metadata.source == 'material_crop'
    assert parsed(result)['materials'] == {'polyester': 75, 'rayon': 21, 'spandex': 4}
    assert parsed(result)['status'] == 'success'


def test_digit_substitution_waits_for_both_independent_rereads(monkeypatch):
    content, _payloads, calls = reread_fixture(monkeypatch, ratio='74%')
    result = run_ocr_bytes(content)
    assert calls == ['original', 'preprocessed', 'material_crop', 'material_crop_rotated']
    assert parsed(result)['status'] == 'success'
    assert parsed(result)['materials']['polyester'] == 75


@pytest.mark.parametrize('failure', ['unknown', 'outside_ratio'])
def test_reread_cannot_hide_unknown_fiber_or_cropped_out_ratio(monkeypatch, failure):
    content, _payloads, calls = reread_fixture(monkeypatch, material='OLEFIN' if failure == 'unknown' else 'Polyester',
                                              extra=failure == 'outside_ratio')
    result = run_ocr_bytes(content)
    assert len(calls) == 4
    assert parsed(result)['status'] == 'failed'


@pytest.mark.parametrize('disabled_by', ['argument', 'environment'])
def test_reread_can_be_disabled_for_baseline_comparison(monkeypatch, disabled_by):
    content, _payloads, calls = reread_fixture(monkeypatch)
    kwargs = {'enable_material_region': False} if disabled_by == 'argument' else {}
    if disabled_by == 'environment':
        monkeypatch.setenv('KDPP_ENABLE_MATERIAL_REGION_OCR', '0')
    assert parsed(run_ocr_bytes(content, **kwargs))['status'] == 'failed'
    assert calls == ['original', 'preprocessed']


def test_valid_original_is_returned_without_any_crop(monkeypatch):
    content, payloads, calls = reread_fixture(monkeypatch)
    payloads[content] = ('original', OcrPayload('Cotton 100%', layout_words=(OcrWord('Cotton', 100, 240, 220, 260), OcrWord('100%', 350, 240, 400, 260))))
    result = run_ocr_bytes(content)
    assert parsed(result)['status'] == 'success'
    assert calls == ['original']


def test_failed_optional_rereads_keep_original_failure(monkeypatch):
    content, _payloads, calls = reread_fixture(monkeypatch)
    provider = ocr_text._run_google_ocr
    def fail_crop(client, candidate_content, **kwargs):
        if len(calls) >= 2:
            raise OcrUnavailableError('provider failure')
        return provider(client, candidate_content, **kwargs)
    monkeypatch.setattr(ocr_text, '_run_google_ocr', fail_crop)
    result = run_ocr_bytes(content)
    assert parsed(result)['status'] == 'failed'
    assert result.metadata.attempt_count == 4
    assert len(result.metadata.attempt_failures) == 2


def test_offline_crop_cache_misses_never_create_client(monkeypatch, tmp_path):
    content, payloads, _calls = reread_fixture(monkeypatch)
    cache = OcrTextCache(tmp_path/'ocr_cache.json')
    for candidate_content, (source, payload) in payloads.items():
        if source in {'original', 'preprocessed'}:
            cache.put(candidate_content, payload.text, source=source, layout_words=payload.layout_words)
    def forbid(*args, **kwargs):
        pytest.fail('offline execution created a client')
    monkeypatch.setattr(ocr_text, '_get_vision_client', forbid)
    result = run_ocr_bytes(content, offline=True, ocr_cache=cache)
    assert parsed(result)['status'] == 'failed'
    assert result.metadata.external_call_count == 0
    assert result.metadata.rpc_attempt_count == 0
    assert len(cache) == 2
    assert image_sha256(content) in cache._entries


def test_elapsed_total_budget_prevents_crop_generation(monkeypatch):
    content, _payloads, calls = reread_fixture(monkeypatch)
    provider = ocr_text._run_google_ocr
    clock = [0.0]
    def slow_preprocessed(client, candidate_content, **kwargs):
        payload = provider(client, candidate_content, **kwargs)
        if calls[-1] == 'preprocessed':
            clock[0] = 26.0
        return payload
    monkeypatch.setattr(ocr_text.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(ocr_text, '_run_google_ocr', slow_preprocessed)
    monkeypatch.setattr(ocr_text, 'prepare_material_region', lambda *args, **kwargs: pytest.fail('budget exhausted'))
    result = run_ocr_bytes(content)
    assert calls == ['original', 'preprocessed']
    assert 'material_crop:total_timeout' in result.metadata.attempt_failures


def test_runtime_bundle_includes_geometry_dependencies(tmp_path):
    import os
    import subprocess
    import sys
    from scripts.build_text_runtime import build_runtime_bundle

    bundle = tmp_path/'runtime'
    build_runtime_bundle(bundle)
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(bundle)
    code = '''from apps.text.ocr_text import OcrPayload, _build_payload_candidates
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import find_material_region
words=(OcrWord('Cotton',100,240,220,260),OcrWord('100%',350,240,400,260))
candidates=_build_payload_candidates('original',OcrPayload('Cotton 100%',layout_words=words),image_key='same',image_variant_key='original',image_transform=(1,0,0,0,1,0),image_region=(0,0,800,600))
assert candidates[0].image_words
assert find_material_region(candidates,800,600) is not None
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=bundle, env=environment,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
