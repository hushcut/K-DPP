from io import BytesIO

from PIL import Image, ImageDraw, ImageStat
import pytest

from apps.text.ocr_errors import InvalidImageError
from apps.text.ocr_regions import _mild_local_contrast, prepare_material_region


def content(image):
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def gradient():
    image = Image.new('L', (480, 240))
    draw = ImageDraw.Draw(image)
    for x in range(480):
        value = round(135 + 100 * x / 479)
        draw.line((x, 0, x, 239), fill=value)
    for x in (100, 350):
        value = round(135 + 100 * x / 479)
        draw.line((x, 80, x, 150), fill=value - 40, width=1)
    return image


@pytest.mark.parametrize('denoise', [False, True])
def test_faint_single_pixel_strokes_survive_light_normalization(denoise):
    original = gradient()
    enhanced = _mild_local_contrast(original, denoise=denoise)
    before_gradient = abs(original.getpixel((100, 30)) - original.getpixel((350, 30)))
    after_gradient = abs(enhanced.getpixel((100, 30)) - enhanced.getpixel((350, 30)))
    assert after_gradient < before_gradient / 2
    for x in (100, 350):
        assert enhanced.getpixel((x + 5, 110)) - enhanced.getpixel((x, 110)) >= 30


def test_weak_median_blend_reduces_speckles_without_erasing_thin_dark_strokes():
    image = Image.new('L', (200, 150), 210)
    draw = ImageDraw.Draw(image)
    for x in range(10, 100, 4):
        for y in range(10, 100, 4):
            draw.point((x, y), fill=175)
    draw.line((150, 20, 150, 100), fill=20, width=1)
    plain = _mild_local_contrast(image)
    denoised = _mild_local_contrast(image, denoise=True)
    assert ImageStat.Stat(denoised.crop((10, 10, 100, 100))).stddev[0] < ImageStat.Stat(
        plain.crop((10, 10, 100, 100))).stddev[0]
    assert denoised.getpixel((150, 70)) < 80
    assert denoised.getpixel((150, 70)) + 130 < denoised.getpixel((160, 70))


def test_rotated_original_color_crop_has_white_corners():
    image = Image.new('RGB', (320, 240), (190, 190, 190))
    result = prepare_material_region(content(image), (0, 0, 320, 240), rotated=True,
                                     rotation_degrees=12, enhancement='original')
    with Image.open(BytesIO(result.content)) as decoded:
        pixel = decoded.convert('RGB').getpixel((2, 2))
    assert min(pixel) >= 245 and max(pixel) - min(pixel) <= 5


@pytest.mark.parametrize('mode', ['mild_contrast', 'mild_denoise'])
@pytest.mark.parametrize('angle', [0, 6, -6])
def test_new_signal_processing_preserves_region_and_inverse_coordinate_map(mode, angle):
    image = gradient().convert('RGB')
    original = prepare_material_region(content(image), (40, 20, 440, 220), rotated=bool(angle),
        rotation_degrees=angle, font_height=12, enhancement='original')
    result = prepare_material_region(content(image), (40, 20, 440, 220), rotated=bool(angle),
        rotation_degrees=angle, font_height=12, enhancement=mode)
    assert result.region == original.region
    assert result.transform == original.transform
    with Image.open(BytesIO(result.content)) as decoded, Image.open(BytesIO(original.content)) as base:
        assert decoded.size == base.size
        assert decoded.mode == 'L'
        assert decoded.width * decoded.height <= 16_000_000


@pytest.mark.parametrize('mode', ['mild_contrast', 'mild_denoise'])
def test_blank_regions_remain_without_artificial_dark_strokes(mode):
    image = Image.new('L', (300, 120), 200)
    result = prepare_material_region(content(image), (0, 0, 300, 120), enhancement=mode)
    with Image.open(BytesIO(result.content)) as decoded:
        assert min(decoded.getextrema()) >= 215
        assert max(decoded.getextrema()) - min(decoded.getextrema()) <= 1


@pytest.mark.parametrize('mode', ['mild_contrast', 'mild_denoise'])
@pytest.mark.parametrize('box', [(-1, 0, 200, 100), (0, 0, 500, 240), (0, 0, 0, 100)])
def test_new_modes_preserve_invalid_region_rejection(mode, box):
    with pytest.raises(InvalidImageError):
        prepare_material_region(content(gradient()), box, enhancement=mode)
