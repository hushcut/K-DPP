"""Color rereads must retain the same composition evidence and request budget."""
from dataclasses import replace
from io import BytesIO
import math

from PIL import Image, ImageChops
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_regions import RegionImage, color_material_region_angle, prepare_material_region


BOX = (0, 0, 800, 600)
TEXT = 'POLYESTER\nRAYON\nSPANDEX\nHAND WASH\n61%\n24%\n15%'


def word(text, x, y, width, angle=-7):
    radians = math.radians(angle)
    dx, dy = round(width * math.cos(radians)), round(width * math.sin(radians))
    vertices = ((x, y), (x + dx, y + dy), (x + dx, y + dy + 20), (x, y + 20))
    return OcrWord(text, min(x for x, _ in vertices), min(y for _, y in vertices),
                   max(x for x, _ in vertices), max(y for _, y in vertices), vertices)


def words():
    return tuple(w for name, number, y in [('POLYESTER', '61', 120), ('RAYON', '24', 190), ('SPANDEX', '15', 260)]
                 for w in (word(name, 100, y, 160), word(number, 450, y - 43, 40), word('%', 495, y - 48, 16))) + (
                     word('HAND', 100, 400, 100), word('WASH', 230, 385, 100),
                 )


def candidates():
    return ocr_text._build_payload_candidates(
        'original', ocr_text.OcrPayload(TEXT, layout_words=words()), image_key='same-image',
        image_variant_key='original-pixels', image_transform=(1, 0, 0, 0, 1, 0), image_region=BOX,
    )


def test_complete_names_and_ratios_use_all_supported_word_polygons():
    source = candidates()
    assert source[0].parser_status == 'failed'
    assert color_material_region_angle(source, BOX, -6.5) == -7
    assert color_material_region_angle(source + source, BOX, -6.5) == -7
    processed = [replace(source[0], source='preprocessed', image_variant_key='processed-pixels')]
    assert color_material_region_angle(processed + source, BOX, -6.5) == -7
    assert color_material_region_angle(source + processed, BOX, -6.5) == -7


def test_color_selection_does_not_depend_on_three_materials():
    source = replace(candidates()[0], observed_materials={'generic': ['cotton', 'polyester', 'rayon', 'spandex']},
                     observed_ratios={'generic': [51, 24, 20, 5]})
    assert color_material_region_angle([source], BOX, -6.5) == -7


@pytest.mark.parametrize('defect', [
    'missing_name', 'repeated_name', 'missing_ratio', 'wrong_total', 'negative_ratio',
    'other_part', 'unknown_fiber', 'invalid_ratio', 'conflict', 'already_confirmed',
    'missing_image', 'other_image', 'missing_variant', 'missing_frame', 'crop_only',
    'missing_polygons', 'other_page', 'different_angle', 'outside_region',
])
def test_uncertain_evidence_keeps_the_existing_input(defect):
    source = candidates()[0]
    additional = []
    box = BOX
    angle = -6.5
    if defect == 'missing_name':
        source = replace(source, observed_materials={'generic': ['polyester', 'spandex']})
    elif defect == 'repeated_name':
        source = replace(source, observed_materials={'generic': ['polyester', 'polyester', 'spandex']})
    elif defect == 'missing_ratio':
        source = replace(source, observed_ratios={'generic': [61, 15]})
    elif defect == 'wrong_total':
        source = replace(source, observed_ratios={'generic': [61, 23, 15]})
    elif defect == 'negative_ratio':
        source = replace(source, observed_ratios={'generic': [101, -16, 15]})
    elif defect == 'other_part':
        source = replace(source, observed_materials={'outer': ['polyester', 'rayon', 'spandex']})
    elif defect in {'unknown_fiber', 'invalid_ratio'}:
        reason = 'unresolved_material_token' if defect == 'unknown_fiber' else 'invalid_composition_evidence'
        source = replace(source, rejected_composition_parts={'generic': ('unpaired_material_rows', reason)})
    elif defect == 'conflict':
        source = replace(source, conflicting_parts=('generic',))
    elif defect == 'already_confirmed':
        source = replace(source, parser_status='success')
    elif defect == 'missing_image':
        source = replace(source, image_key='')
    elif defect == 'other_image':
        additional = [replace(source, image_key='another-image')]
    elif defect == 'missing_variant':
        source = replace(source, image_variant_key='')
    elif defect == 'missing_frame':
        source = replace(source, image_region=())
    elif defect == 'crop_only':
        source = replace(source, source='material_crop')
    elif defect == 'missing_polygons':
        source = replace(source, image_words=tuple(replace(w, vertices=()) for w in source.image_words))
    elif defect == 'other_page':
        source = replace(source, image_words=tuple(replace(w, page=1) for w in source.image_words))
    elif defect == 'different_angle':
        angle = -12
    else:
        box = (600, 500, 800, 600)
    assert color_material_region_angle([source] + additional, box, angle) is None


@pytest.mark.parametrize('angle', [0, -3, -4.5, 45, -45, 90, -90])
def test_horizontal_and_sideways_labels_keep_the_existing_input(angle):
    assert color_material_region_angle(candidates(), BOX, angle) is None


@pytest.mark.parametrize('outcome', ['success', 'service_error', 'wrong_ratio', 'unknown_name'])
def test_product_path_replaces_the_last_input_and_keeps_failure_evidence(monkeypatch, outcome):
    monkeypatch.setattr(ocr_text, 'validate_image_bytes', lambda *_args, **_kwargs: (
        ocr_text.ValidatedImage(b'original', 'PNG', 800, 600)
    ))
    monkeypatch.setattr(ocr_text, '_resolve_credential_path', lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *_args: object())
    monkeypatch.setattr(ocr_text, 'preprocess_image_bytes', lambda _content: b'processed')
    monkeypatch.setattr(ocr_text, 'ocr_coordinate_frame', lambda *_args: ((1, 0, 0, 0, 1, 0), BOX))
    monkeypatch.setattr(ocr_text, 'find_material_region', lambda *_args: BOX)
    monkeypatch.setattr(ocr_text, 'find_complete_material_region', lambda *_args: None)
    monkeypatch.setattr(ocr_text, 'material_region_options', lambda *_args: (20, -6.5))
    prepared = []
    calls = []

    def prepare(_content, box, **kwargs):
        prepared.append(kwargs)
        content = b'color' if kwargs['rotated'] else b'plain'
        return RegionImage(content, 'material_crop_rotated' if kwargs['rotated'] else 'material_crop',
                           (1, 0, 0, 0, 1, 0), box, kwargs['enhancement'])

    def provider(_client, content, **_kwargs):
        calls.append(content)
        if content != b'color':
            return ocr_text.OcrPayload(TEXT, layout_words=words())
        if outcome == 'service_error':
            raise ocr_text.OcrUnavailableError('temporary')
        text = 'POLYESTER 61%\nRAYON 24%\nSPANDEX 15%'
        if outcome == 'wrong_ratio':
            text = text.replace('61', '60').replace('24', '25')
        elif outcome == 'unknown_name':
            text = text.replace('POLYESTER', 'UNREGISTEREDFIBER')
        return ocr_text.OcrPayload(text, layout_words=words())

    monkeypatch.setattr(ocr_text, 'prepare_material_region', prepare)
    monkeypatch.setattr(ocr_text, '_run_google_ocr', provider)
    result = analyze_ocr_result(ocr_text.run_ocr_bytes(b'image',
        enable_reflection=False, enable_denoised=False, enable_rotated=False, enable_material_region=True))
    assert calls == [b'original', b'processed', b'plain', b'color']
    assert prepared[-1]['enhancement'] == 'original'
    assert prepared[-1]['rotation_degrees'] == -7
    assert result['ocr']['attempt_count'] == 4
    if outcome == 'success':
        assert result['status'] == 'success'
        assert result['materials'] == {'polyester': 61, 'rayon': 24, 'spandex': 15}
    else:
        assert result['status'] == 'failed'
        assert result['materials'] == {}


def test_selected_input_retains_color_and_the_coordinate_map():
    image = Image.new('RGB', (800, 600), 'white')
    image.paste('red', (150, 170, 170, 190))
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    reread = prepare_material_region(buffer.getvalue(), (50, 50, 550, 450),
        rotated=True, rotation_degrees=-7, font_height=20, enhancement='original')
    with Image.open(BytesIO(reread.content)) as output:
        assert output.mode == 'RGB'
        red, green, blue = output.split()
        above_green = ImageChops.subtract(red, green).point(lambda value: 255 if value > 80 else 0)
        above_blue = ImageChops.subtract(red, blue).point(lambda value: 255 if value > 80 else 0)
        bounds = ImageChops.darker(above_green, above_blue).getbbox()
        assert bounds is not None
        assert output.width * output.height <= 16_000_000
    x, y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    a, b, c, d, e, f = reread.transform
    assert a * x + b * y + c == pytest.approx(160, abs=2)
    assert d * x + e * y + f == pytest.approx(180, abs=2)
