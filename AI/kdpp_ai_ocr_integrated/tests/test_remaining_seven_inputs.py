"""실사진에서 확인한 번역명과 흐린 인쇄 전처리의 안전 경계."""

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from apps.text.material_extraction import extract_materials
from apps.text.ocr_regions import prepare_material_region
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('name', ['POLIESTERE', 'POLYESTERI', 'POLIESTERIS',
                                 'POLÜESTER', 'ПОЛИЭСТЕР', 'ΠΟΛΥΕΣΤΕΡΑΣ'])
def test_complete_printed_polyester_translations_keep_exact_ratios(name):
    result = parse_label(f'62% {name}\n38% COTTON')
    assert result['status'] == 'success', result
    assert result['materials'] == {'polyester': 62, 'cotton': 38}


@pytest.mark.parametrize('name', ['POLIESTERE', 'POLYESTERI', 'POLIESTERIS',
                                 'POLÜESTER', 'ПОЛИЭСТЕР', 'ΠΟΛΥΕΣΤΕΡΑΣ'])
def test_translation_alias_does_not_match_compound_unknown_fiber(name):
    assert extract_materials('X' + name) == []
    assert parse_label(f'80% COTTON\n20% X{name}')['status'] == 'failed'


@pytest.mark.parametrize('text', [
    'UK: 100% POLYESTER IT: 80% POLIESTERE 20% COTONE',
    'POLIESTERE 62%\nCOTTON 33%',
    'POLIESTERE 100%\nUNKNOWN FIBER 5%',
    'POLIESTERE -100%',
    'POLIÉSTE 62%\nCOTTON 38%',
    'ПОЛИЗСТЕР 100%',
    'POLIESTERIS\nUNKNOWN\n100%',
    'Cotton\nUNKNOWN\n100%',
    'Cotton\nOLEFIN\n100%',
])
def test_translation_registration_cannot_hide_unread_or_conflicting_evidence(text):
    assert parse_label(text)['status'] == 'failed'


def faded_weave():
    image = Image.new('L', (800, 600), 210)
    draw = ImageDraw.Draw(image)
    for x in range(100, 600):
        for y in range(150, 360):
            value = 210 + (4 if (x + y) % 4 < 2 else -4)
            draw.point((x, y), fill=value)
    # One-pixel thin ink inside a textured field, plus a geometric landmark.
    draw.line((350, 190, 350, 315), fill=175, width=1)
    draw.rectangle((195, 230, 205, 240), fill=20)
    stream = BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


@pytest.mark.parametrize('angle', [0, -3, 90])
def test_faint_print_preserves_thin_ink_and_inverse_coordinates(angle):
    image = prepare_material_region(faded_weave(), (100, 150, 600, 360),
                                    enhancement='faint_print', rotated=bool(angle),
                                    rotation_degrees=angle, font_height=24)
    with Image.open(BytesIO(image.content)) as output:
        assert output.width * output.height <= 16_000_000
        a, b, c, d, e, f = image.transform
        det = a * e - b * d
        def intensity(x, y):
            px = round((e * (x - c) - b * (y - f)) / det)
            py = round((-d * (x - c) + a * (y - f)) / det)
            return output.convert('L').getpixel((px, py))
        assert intensity(350, 270) < intensity(365, 270) - 15
        assert intensity(200, 235) < 80


def test_new_filter_is_opt_in_and_keeps_original_input_bytes():
    content = faded_weave()
    first = prepare_material_region(content, (100, 150, 600, 360))
    custom = prepare_material_region(content, (100, 150, 600, 360), enhancement='faint_print')
    last = prepare_material_region(content, (100, 150, 600, 360))
    assert first.content == last.content
    assert custom.content != first.content
    assert custom.region == first.region and custom.transform == first.transform
    assert custom.enhancement == 'faint_print'
