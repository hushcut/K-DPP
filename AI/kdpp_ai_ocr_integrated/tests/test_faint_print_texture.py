"""흐린 인쇄에서 무늬 억제와 획·실패 반환의 실제 경계 검사."""

from io import BytesIO
from statistics import pstdev

from PIL import Image, ImageDraw
import pytest

from apps.service.label_analysis import analyze_label_text
from apps.text.ocr_regions import prepare_material_region


def periodic_texture():
    image = Image.new('L', (800, 600), 210)
    draw = ImageDraw.Draw(image)
    for x in range(100, 600):
        for y in range(150, 360):
            draw.point((x, y), fill=210 + (8 if (x + y) % 4 < 2 else -8))
    draw.line((300, 190, 300, 310), fill=168, width=1)
    stream = BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def pixel_at_original(image, transform, x, y):
    a, b, c, d, e, f = transform
    determinant = a * e - b * d
    px = round((e * (x - c) - b * (y - f)) / determinant)
    py = round((-d * (x - c) + a * (y - f)) / determinant)
    return image.getpixel((px, py))


@pytest.mark.parametrize('font_height', [24, 28.5, 36])
def test_weave_is_suppressed_instead_of_amplified_with_faint_ink(font_height):
    prepared = prepare_material_region(periodic_texture(), (100, 150, 600, 360),
                                       font_height=font_height, enhancement='faint_print')
    with Image.open(BytesIO(prepared.content)) as image:
        gray = image.convert('L')
        area = [pixel_at_original(gray, prepared.transform, x, y)
                for x in range(420, 480) for y in range(230, 250)]
        # The original alternating weave has standard deviation 8.
        assert pstdev(area) < 8 * 0.8
        ink = pixel_at_original(gray, prepared.transform, 300, 270)
        background = pixel_at_original(gray, prepared.transform, 315, 270)
        assert ink < background - 20


def test_flat_surface_does_not_acquire_artificial_ink():
    image = Image.new('L', (800, 600), 210)
    stream = BytesIO()
    image.save(stream, 'PNG')
    prepared = prepare_material_region(stream.getvalue(), (100, 150, 600, 360), enhancement='faint_print')
    with Image.open(BytesIO(prepared.content)) as output:
        minimum, maximum = output.convert('L').getextrema()
        assert minimum == maximum


@pytest.mark.parametrize('text', [
    '섬유의 조성 및 혼용률',
    '섬유의 조성 및 혼용률\n100%\n70%\n폴리에스터\n80%',
    '겉감\n100%',
])
def test_unread_faded_text_still_returns_material_failure(text):
    result = analyze_label_text(text)
    assert result['status'] == 'failed'
    assert result['materials'] == {}
    assert result['error_code'] == 'composition_not_found'
