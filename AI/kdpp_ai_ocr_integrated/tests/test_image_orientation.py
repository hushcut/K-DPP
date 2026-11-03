"""OCR 원본·좌표·크기가 같은 방향 기준을 사용하는지 검증한다."""

from io import BytesIO

import pytest
from PIL import Image

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_image, ocr_text
from apps.text.ocr_layout import OcrWord


COLORS = ((240, 20, 20), (20, 220, 20), (20, 20, 240), (230, 220, 20))
# Expected TL, TR, BL, BR corner identities, independent of EXIF transpose code.
CORNERS = {
    1: (0, 1, 2, 3), 2: (1, 0, 3, 2), 3: (3, 2, 1, 0), 4: (2, 3, 0, 1),
    5: (0, 2, 1, 3), 6: (2, 0, 3, 1), 7: (3, 1, 2, 0), 8: (1, 3, 0, 2),
}


def oriented_image(image_format, orientation=None):
    image = Image.new('RGB', (64, 40))
    for color, bounds in zip(COLORS, ((0, 0, 32, 20), (32, 0, 64, 20),
                                    (0, 20, 32, 40), (32, 20, 64, 40))):
        image.paste(color, bounds)
    options = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        exif[270] = 'input-only metadata'
        options['exif'] = exif
    if image_format in {'MPO', 'JPEG'}:
        options['quality'] = 95
    if image_format == 'MPO':
        options.update(save_all=True, append_images=[Image.new('RGB', image.size, 'black')])
    if image_format == 'WEBP':
        options['lossless'] = True
    buffer = BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


@pytest.mark.parametrize('image_format', ['JPEG', 'PNG', 'WEBP', 'MPO'])
@pytest.mark.parametrize('orientation', range(1, 9))
def test_oriented_input_pixels_size_and_coordinate_frame_agree(image_format, orientation):
    content = oriented_image(image_format, orientation)
    with Image.open(BytesIO(content)) as original:
        assert original.format == image_format
        assert original.getexif()[274] == orientation
    validated = ocr_image.validate_image_bytes(content)
    expected_size = (40, 64) if orientation >= 5 else (64, 40)
    assert (validated.width, validated.height) == expected_size
    # The public format records the input container, including converted MPO.
    assert validated.image_format == image_format
    with Image.open(BytesIO(validated.content)) as upright:
        assert upright.size == expected_size
        assert upright.getexif().get(274, 1) == 1
        if orientation != 1 or image_format == 'MPO':
            assert not upright.getexif(), 'converted input must not retain EXIF'
        assert upright.format == ('JPEG' if image_format == 'MPO' else image_format)
        rgb = upright.convert('RGB')
        width, height = rgb.size
        samples = ((5, 5), (width - 6, 5), (5, height - 6), (width - 6, height - 6))
        for point, color_index in zip(samples, CORNERS[orientation]):
            assert all(abs(actual - expected) <= 15
                       for actual, expected in zip(rgb.getpixel(point), COLORS[color_index]))
    assert ocr_image.ocr_coordinate_frame(validated.content, validated.content, 'original') == (
        (1.0, 0.0, 0.0, 0.0, 1.0, 0.0), (0.0, 0.0, *map(float, expected_size)),
    )
    assert ocr_image.validate_image_bytes(validated.content).content == validated.content


@pytest.mark.parametrize('image_format', ['JPEG', 'PNG', 'WEBP'])
@pytest.mark.parametrize('orientation', [None, 1])
def test_already_upright_input_is_not_reencoded(image_format, orientation):
    content = oriented_image(image_format, orientation)
    assert ocr_image.validate_image_bytes(content).content == content


def damaged_exif_image(image_format):
    buffer = BytesIO()
    # Valid container/pixels, invalid TIFF header inside EXIF. JFIF DPI keeps
    # JPEG's loader from reading and swallowing the EXIF error during open().
    Image.new('RGB', (64, 40), 'white').save(
        buffer, format=image_format, exif=b'Exif\0\0BAD!0000', dpi=(72, 72),
    )
    return buffer.getvalue()


@pytest.mark.parametrize('image_format', ['JPEG', 'PNG', 'WEBP'])
@pytest.mark.parametrize('operation', [
    'validate_image_bytes', 'preprocess_image_bytes', 'preprocess_denoised_image_bytes',
    'preprocess_rotated_image_bytes', 'preprocess_reflection_image_bytes', 'ocr_coordinate_frame',
])
def test_readable_pixels_with_broken_exif_raise_a_controlled_input_error(image_format, operation):
    content = damaged_exif_image(image_format)
    with Image.open(BytesIO(content)) as image:
        image.load()  # The failure is metadata, not a fabricated unreadable image.
        assert image.size == (64, 40)
        if image_format == 'JPEG':
            assert image.info['dpi'] == (72, 72)
    with pytest.raises(ocr_image.InvalidImageError) as caught:
        if operation == 'ocr_coordinate_frame':
            ocr_image.ocr_coordinate_frame(content, oriented_image('PNG'), 'original')
        else:
            getattr(ocr_image, operation)(content)
    assert isinstance(caught.value.__cause__, SyntaxError)


def forbid_vision(*_args, **_kwargs):
    pytest.fail('invalid image must stop before Vision client creation or RPC')


@pytest.mark.parametrize('image_format', ['JPEG', 'PNG', 'WEBP'])
def test_broken_exif_stops_before_vision_client_creation(monkeypatch, image_format):
    monkeypatch.setattr(ocr_text, '_get_vision_client', forbid_vision)
    monkeypatch.setattr(ocr_text, '_run_google_ocr', forbid_vision)
    with pytest.raises(ocr_image.InvalidImageError):
        ocr_text.run_ocr_bytes(damaged_exif_image(image_format))


@pytest.mark.parametrize('orientation', [2, 6, 8])
def test_truncated_oriented_jpeg_is_rejected_before_vision(monkeypatch, orientation):
    content = oriented_image('JPEG', orientation)[:-8]
    # JPEG verify() checks the header; the required orientation transform must
    # still decode the pixels and reject missing data without a raw fallback.
    with Image.open(BytesIO(content)) as image:
        assert image.getexif()[274] == orientation
        image.verify()
    monkeypatch.setattr(ocr_text, '_get_vision_client', forbid_vision)
    monkeypatch.setattr(ocr_text, '_run_google_ocr', forbid_vision)
    with pytest.raises(ocr_image.InvalidImageError):
        ocr_text.run_ocr_bytes(content)


def test_transformed_candidate_maps_into_upright_input_frame():
    validated = ocr_image.validate_image_bytes(oriented_image('JPEG', 6))
    buffer = BytesIO()
    Image.new('RGB', (20, 32)).save(buffer, format='PNG')
    assert ocr_image.ocr_coordinate_frame(validated.content, buffer.getvalue(), 'preprocessed') == (
        (2.0, 0.0, 0.0, 0.0, 2.0, 0.0), (0.0, 0.0, 40.0, 64.0),
    )


def test_oriented_conversion_still_enforces_output_byte_limit(monkeypatch):
    content = oriented_image('WEBP', 6)
    monkeypatch.setattr(ocr_image, 'MAX_IMAGE_BYTES', len(content))
    # A lossless PNG-like arrangement can get larger when rotated and encoded;
    # force that boundary independently of the codec's compression ratio.
    original_save = Image.Image.save

    def oversized_save(image, output, **kwargs):
        original_save(image, output, **kwargs)
        output.write(b'padding' * len(content))

    monkeypatch.setattr(Image.Image, 'save', oversized_save)
    with pytest.raises(ocr_image.ImageTooLargeError):
        ocr_image.validate_image_bytes(content)


@pytest.mark.parametrize('image_format', ['JPEG', 'PNG', 'WEBP', 'MPO'])
def test_original_ocr_uses_upright_geometry_to_recover_two_column_row(monkeypatch, image_format):
    buffer = BytesIO()
    image = Image.new('RGB', (200, 400), 'white')
    exif = Image.Exif()
    exif[274] = 6
    options = {'save_all': True, 'append_images': [image]} if image_format == 'MPO' else {}
    image.save(buffer, format=image_format, exif=exif, **options)
    words = tuple(OcrWord(text, left, top, right, bottom,
                          ((left, top), (right, top), (right, bottom), (left, bottom)))
                  for text, left, top, right, bottom in (
                      ('OUTER', 10, 20, 70, 40), ('COTTON', 130, 20, 220, 40),
                      ('100%', 240, 20, 300, 40), ('LINING', 10, 80, 80, 100),
                  ))
    calls = []

    def fake_vision(_client, content, **_kwargs):
        calls.append(content)
        with Image.open(BytesIO(content)) as upright:
            assert upright.size == (400, 200)
            assert upright.getexif().get(274, 1) == 1
        return ocr_text.OcrPayload('OUTER\nLINING\nCOTTON 100%',
                                   'OUTER COTTON 100%\nLINING', layout_words=words)

    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *_args: object())
    monkeypatch.setattr(ocr_text, '_run_google_ocr', fake_vision)
    result = analyze_ocr_result(ocr_text.run_ocr_bytes(
        buffer.getvalue(), enable_reflection=False, enable_denoised=False,
        enable_rotated=False, enable_material_region=True,
    ))
    assert len(calls) == 1
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': 100}
    assert (result['ocr']['width'], result['ocr']['height']) == (400, 200)
