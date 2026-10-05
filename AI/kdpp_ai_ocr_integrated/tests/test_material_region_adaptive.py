from dataclasses import replace
from io import BytesIO
import math

import pytest
from PIL import Image, ImageDraw

from apps.text.ocr_errors import InvalidImageError
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import find_material_region, prepare_material_region
from apps.text.ocr_text import OcrPayload, _build_payload_candidates


def candidates(words):
    return _build_payload_candidates('original', OcrPayload('\n'.join(w.text for w in words), layout_words=words),
        image_key='image', image_variant_key='original', image_transform=(1, 0, 0, 0, 1, 0),
        image_region=(0, 0, 800, 600))


def angled_word(text, x, y, angle):
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    points = tuple((round(x + cosine * dx - sine * dy), round(y + sine * dx + cosine * dy))
                   for dx, dy in ((0, 0), (130, 0), (130, 20), (0, 20)))
    return OcrWord(text, min(p[0] for p in points), min(p[1] for p in points),
                   max(p[0] for p in points), max(p[1] for p in points), points)


def test_missing_percent_can_locate_two_known_fibers_without_fixing_ratios():
    words = (OcrWord('Cotton', 250, 250, 350, 270), OcrWord('9596', 400, 250, 470, 270),
             OcrWord('Span', 250, 295, 350, 315), OcrWord('596', 400, 295, 460, 315))
    sources = candidates(words)
    assert all(c.parser_status == 'failed' for c in sources)
    box = find_material_region(sources, 800, 600)
    assert box is not None
    assert all(box[0] <= w.left < w.right <= box[2] and box[1] <= w.top < w.bottom <= box[3] for w in words)


@pytest.mark.parametrize('failure', ['single_fiber', 'no_number', 'far_numbers', 'only_numbers', 'no_frame'])
def test_missing_percent_fallback_requires_material_and_numeric_rows(failure):
    words = (OcrWord('Cotton', 250, 250, 350, 270), OcrWord('9596', 400, 250, 470, 270),
             OcrWord('Span', 250, 295, 350, 315), OcrWord('596', 400, 295, 460, 315))
    if failure == 'single_fiber':
        words = words[:2]
    elif failure == 'no_number':
        words = tuple(w for w in words if not w.text.isdecimal())
    elif failure == 'far_numbers':
        words = tuple(replace(w, top=w.top + 200, bottom=w.bottom + 200) if w.text.isdecimal() else w for w in words)
    elif failure == 'only_numbers':
        words = tuple(w for w in words if w.text.isdecimal())
    sources = candidates(words)
    if failure == 'no_frame':
        sources = [replace(c, image_region=()) for c in sources]
    assert find_material_region(sources, 800, 600) is None


@pytest.mark.parametrize('angle', [-90, 90])
def test_sideways_text_uses_glyph_thickness_for_a_local_region(angle):
    x, y = (260, 400) if angle < 0 else (260, 210)
    words = (angled_word('COTTON', x, y, angle), angled_word('COTON', x + 45, y, angle),
             OcrWord('100%', x - 5, 430 if angle < 0 else 355, x + 20, 490 if angle < 0 else 415))
    box = find_material_region(candidates(words), 800, 600)
    assert box is not None
    assert (box[2] - box[0]) * (box[3] - box[1]) < 0.5 * 800 * 600
    assert all(box[0] <= w.left < w.right <= box[2] and box[1] <= w.top < w.bottom <= box[3] for w in words)


@pytest.mark.parametrize('angle', [-90, -6, 6, 90])
def test_rotation_options_follow_supported_word_direction(angle):
    from apps.text.ocr_regions import material_region_options
    x, y = (250, 350) if angle < 0 else (250, 150)
    words = (angled_word('Cotton', x, y, angle), angled_word('Spandex', x + 60, y + 50, angle))
    sources = candidates(words)
    height, correction = material_region_options(sources, (0, 0, 800, 600))
    assert correction == pytest.approx(angle, abs=0.5)
    assert height == pytest.approx(20, abs=1)
    assert material_region_options(list(reversed(sources)), (0, 0, 800, 600)) == (height, correction)


@pytest.mark.parametrize('failure', ['single_box', 'same_physical_box', 'mixed_direction', 'out_of_region'])
def test_uncertain_orientation_keeps_existing_small_rotation(failure):
    from apps.text.ocr_regions import material_region_options
    words = (angled_word('Cotton', 200, 180, 5), angled_word('Spandex', 200, 240, 5))
    if failure == 'single_box':
        words = words[:1]
    elif failure == 'same_physical_box':
        words = (words[0], replace(words[0], left=words[0].left + 1, right=words[0].right + 1))
    elif failure == 'mixed_direction':
        words = (words[0], angled_word('Spandex', 200, 240, -5))
    box = (0, 0, 800, 100) if failure == 'out_of_region' else (0, 0, 800, 600)
    assert material_region_options(candidates(words), box)[1] == -3


def image_bytes():
    image = Image.new('RGB', (800, 600), 'white')
    ImageDraw.Draw(image).rectangle((150, 250, 170, 270), fill='black')
    buffer = BytesIO()
    image.save(buffer, format='JPEG')
    return buffer.getvalue()


@pytest.mark.parametrize('angle', [-90, -5.5, 5.5, 90])
def test_adaptive_rotation_inverse_map_matches_actual_pixels(angle):
    cropped = prepare_material_region(image_bytes(), (60, 190, 440, 390), rotated=True,
                                      rotation_degrees=angle, font_height=8)
    with Image.open(BytesIO(cropped.content)) as image:
        assert image.width * image.height <= 16_000_000
        bbox = image.convert('L').point(lambda value: 255 if value < 80 else 0).getbbox()
    x, y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    a, b, c, d, e, f = cropped.transform
    assert a * x + b * y + c == pytest.approx(160, abs=2)
    assert d * x + e * y + f == pytest.approx(260, abs=2)


def test_font_height_can_enlarge_small_text_within_existing_limits():
    original = prepare_material_region(image_bytes(), (0, 0, 800, 600))
    enlarged = prepare_material_region(image_bytes(), (0, 0, 800, 600), font_height=10)
    with Image.open(BytesIO(original.content)) as first, Image.open(BytesIO(enlarged.content)) as second:
        assert second.width > first.width
        assert second.width <= 3200
        assert second.width * second.height <= 16_000_000


@pytest.mark.parametrize('value', [-1, 0, float('nan'), float('inf'), True, '20'])
def test_invalid_font_height_is_rejected(value):
    with pytest.raises(InvalidImageError):
        prepare_material_region(image_bytes(), (60, 190, 440, 390), font_height=value)


@pytest.mark.parametrize('value', [181, -181, float('nan'), float('inf'), True, '-3'])
def test_invalid_rotation_angle_is_rejected(value):
    with pytest.raises(InvalidImageError):
        prepare_material_region(image_bytes(), (60, 190, 440, 390), rotated=True, rotation_degrees=value)
