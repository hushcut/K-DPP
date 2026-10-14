"""소재 표 제목·불균일 조명·역좌표와 호출 한도 회귀 검사."""

from dataclasses import replace
from io import BytesIO
import math

import pytest
from PIL import Image, ImageDraw, ImageStat

from apps.text import ocr_text
from apps.text.ocr_errors import InvalidImageError
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import find_material_region, material_region_options, prepare_material_region
from apps.text.ocr_text import OcrPayload, _build_payload_candidates
from apps.text.parse_label import parse_label


def candidates(words):
    return _build_payload_candidates('original', OcrPayload('\n'.join(w.text for w in words), layout_words=words),
        image_key='same-image', image_variant_key='raw', image_transform=(1, 0, 0, 0, 1, 0),
        image_region=(0, 0, 800, 600))


def header_words():
    return (OcrWord('섬유', 220, 200, 270, 225), OcrWord('조성', 320, 200, 365, 225),
            OcrWord('혼용', 430, 200, 475, 225))


def test_composition_header_locates_unread_table_without_inventing_material():
    words = header_words()
    sources = candidates(words)
    box = find_material_region(sources, 800, 600)
    assert box is not None
    assert box[0] < 220 and box[2] > 475
    assert box[1] <= 200 and box[3] >= 325
    assert (box[2] - box[0]) * (box[3] - box[1]) < 800 * 600 / 2
    assert parse_label(sources[0].text)['status'] == 'failed'
    assert find_material_region(list(reversed(sources)) + sources, 800, 600) == box


@pytest.mark.parametrize('failure', ['composition_only', 'blend_only', 'far', 'multiple_headers',
                                   'no_frame', 'no_variant', 'page', 'outside', 'thumbnail'])
def test_header_region_requires_a_local_verified_composition_title(failure):
    words = header_words()
    if failure == 'composition_only':
        words = words[:2]
    elif failure == 'blend_only':
        words = words[2:]
    elif failure == 'far':
        words = (*words[:2], replace(words[2], top=480, bottom=505))
    elif failure == 'multiple_headers':
        words += tuple(replace(w, top=w.top+200, bottom=w.bottom+200) for w in words)
    elif failure == 'page':
        words = tuple(replace(w, page=1) for w in words)
    elif failure == 'outside':
        words = tuple(replace(w, left=-20, right=-1) for w in words)
    sources = candidates(words)
    if failure == 'no_frame':
        sources = [replace(c, image_region=()) for c in sources]
    elif failure == 'no_variant':
        sources = [replace(c, image_variant_key='') for c in sources]
    assert find_material_region(sources, *(400, 400) if failure == 'thumbnail' else (800, 600)) is None


def test_header_cannot_crop_out_another_observed_percentage():
    words = header_words() + (OcrWord('Cotton', 220, 250, 350, 270),
                              OcrWord('100%', 430, 250, 485, 270),
                              OcrWord('UNKNOWN', 220, 450, 380, 470),
                              OcrWord('20%', 430, 450, 485, 470))
    box = find_material_region(candidates(words), 800, 600)
    assert box is not None and box[3] >= 470
    assert parse_label('\n'.join(w.text for w in words))['status'] == 'failed'


def tilted(text, x, y, angle):
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    points = tuple((round(x+cosine*dx-sine*dy), round(y+sine*dx+cosine*dy))
                   for dx, dy in ((0, 0), (100, 0), (100, 20), (0, 20)))
    return OcrWord(text, min(x for x, y in points), min(y for x, y in points),
                   max(x for x, y in points), max(y for x, y in points), points)


@pytest.mark.parametrize('angle', [-6, 6])
def test_header_word_direction_is_available_when_material_names_are_missing(angle):
    words = (tilted('조성', 200, 200, angle), tilted('혼용', 350, 200, angle))
    height, correction = material_region_options(candidates(words), (0, 0, 800, 600))
    assert height == pytest.approx(20, abs=1)
    assert correction == pytest.approx(angle, abs=0.5)


def image_bytes(uneven=True):
    image = Image.new('RGB', (800, 600), 'white')
    draw = ImageDraw.Draw(image)
    if uneven:
        for x in range(800):
            value = round(130 + 115*x/799)
            draw.line((x, 0, x, 599), fill=(value, value, value))
        for x in (160, 600):
            value = round(130 + 115*x/799) - 25
            draw.rectangle((x-5, 240, x+5, 280), fill=(value, value, value))
    else:
        draw.rectangle((155, 250, 165, 270), fill='black')
    buffer = BytesIO()
    image.save(buffer, format='JPEG')
    return buffer.getvalue()


def sample(image, result, x, y):
    a, b, c, d, e, f = result.transform
    determinant = a*e-b*d
    ix, iy = (e*(x-c)-b*(y-f))/determinant, (-d*(x-c)+a*(y-f))/determinant
    return ImageStat.Stat(image.crop((round(ix)-2, round(iy)-2, round(ix)+3, round(iy)+3))).median[0]


def test_local_contrast_reduces_background_gradient_and_preserves_dark_strokes():
    content = image_bytes()
    original = prepare_material_region(content, (0, 100, 800, 450), enhancement='original')
    corrected = prepare_material_region(content, (0, 100, 800, 450), enhancement='local_contrast')
    with Image.open(BytesIO(original.content)) as raw, Image.open(BytesIO(corrected.content)) as enhanced:
        raw = raw.convert('L')
        enhanced = enhanced.convert('L')
        before = abs(sample(raw, original, 160, 180)-sample(raw, original, 600, 180))
        after = abs(sample(enhanced, corrected, 160, 180)-sample(enhanced, corrected, 600, 180))
        assert after < before/2
        for x in (160, 600):
            assert sample(enhanced, corrected, x, 180)-sample(enhanced, corrected, x, 260) > 40


def test_uniform_background_keeps_the_existing_candidate_bytes():
    content = image_bytes(uneven=False)
    box = (60, 190, 440, 390)
    original = prepare_material_region(content, box, rotated=True)
    adaptive = prepare_material_region(content, box, rotated=True, enhancement='adaptive')
    assert adaptive.enhancement == 'standard'
    assert adaptive.content == original.content
    assert adaptive.transform == original.transform


def test_nonuniform_background_selects_local_contrast_without_changing_geometry():
    content = image_bytes()
    original = prepare_material_region(content, (0, 100, 800, 450), rotated=True, rotation_degrees=6)
    adaptive = prepare_material_region(content, (0, 100, 800, 450), rotated=True,
                                       rotation_degrees=6, enhancement='adaptive')
    assert adaptive.enhancement == 'local_contrast'
    assert adaptive.content != original.content
    assert adaptive.transform == original.transform
    assert adaptive.region == original.region
    with Image.open(BytesIO(adaptive.content)) as image:
        assert image.width*image.height <= 16_000_000


def test_faint_print_on_uniform_background_also_selects_local_contrast():
    image = Image.new('L', (800, 600), 190)
    draw = ImageDraw.Draw(image)
    for y in range(120, 400, 45):
        draw.rectangle((180, y, 600, y+12), fill=155)
    buffer = BytesIO()
    image.save(buffer, format='JPEG')
    corrected = prepare_material_region(buffer.getvalue(), (100, 80, 700, 440), enhancement='adaptive')
    assert corrected.enhancement == 'local_contrast'


def test_completely_blank_uniform_region_is_not_treated_as_faint_print():
    image = Image.new('L', (800, 600), 190)
    buffer = BytesIO()
    image.save(buffer, format='JPEG')
    corrected = prepare_material_region(buffer.getvalue(), (100, 80, 700, 440), enhancement='adaptive')
    assert corrected.enhancement == 'standard'


@pytest.mark.parametrize('mode', ['', 'glare', None, True, 1, []])
def test_unknown_preprocessing_modes_are_rejected(mode):
    with pytest.raises(InvalidImageError):
        prepare_material_region(image_bytes(), (60, 190, 440, 390), enhancement=mode)


def test_adaptive_preprocessing_uses_the_existing_second_crop_slot(monkeypatch):
    content = image_bytes()
    words = (OcrWord('Cotton', 220, 240, 350, 260), OcrWord('95%', 430, 240, 485, 260),
             OcrWord('UNKNOWN', 220, 280, 380, 300), OcrWord('5%', 430, 280, 485, 300))
    calls, crop_options = [], []
    def provider(_client, data, **kwargs):
        calls.append(data)
        return OcrPayload('Cotton 95%\nUNKNOWN 5%', layout_words=words)
    def prepare(data, box, **kwargs):
        crop_options.append((kwargs['rotated'], kwargs['enhancement']))
        return prepare_material_region(data, box, **kwargs)
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *args: object())
    monkeypatch.setattr(ocr_text, '_resolve_credential_path', lambda *args: (None, None))
    monkeypatch.setattr(ocr_text, '_run_google_ocr', provider)
    monkeypatch.setattr(ocr_text, 'prepare_material_region', prepare)
    result = ocr_text.run_ocr_bytes(content, enable_reflection=False, enable_denoised=False,
                                  enable_rotated=False, enable_material_region=True)
    assert len(calls) == 4
    assert crop_options == [(False, 'standard'), (True, 'adaptive_mild')]
    assert parse_label(result.text, rejected_composition_parts=result.metadata.rejected_composition_parts,
                       conflicting_parts=result.metadata.conflicting_parts,
                       unpaired_ratio_parts=result.metadata.unpaired_ratio_parts)['status'] == 'failed'
