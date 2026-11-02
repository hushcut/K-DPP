"""기존 호출 슬롯의 약한 대비 보정·좌표·캐시·획 보존 검사."""

from io import BytesIO

from PIL import Image, ImageDraw
import pytest

from apps.text.ocr_regions import prepare_material_region


def photo(gradient=False):
    image = Image.new('L', (500, 240), 240)
    if gradient:
        draw = ImageDraw.Draw(image)
        for x in range(500):
            draw.line((x, 0, x, 239), fill=80 + x * 170 // 499)
    draw = ImageDraw.Draw(image)
    for x in (190, 200, 230):
        draw.line((x, 60, x, 170), fill=0, width=1)
    encoded = BytesIO()
    image.save(encoded, format='PNG')
    return encoded.getvalue()


def test_uniform_background_second_slot_uses_mild_contrast_after_enlargement():
    content = photo()
    box = (100, 20, 400, 210)
    automatic = prepare_material_region(content, box, rotated=True, rotation_degrees=0,
                                        enhancement='adaptive_mild')
    manual = prepare_material_region(content, box, rotated=True, rotation_degrees=0,
                                     enhancement='mild_contrast')
    assert automatic.enhancement == 'mild_contrast'
    assert automatic.content == manual.content
    assert automatic.transform == manual.transform
    assert automatic.region == manual.region
    with Image.open(BytesIO(automatic.content)) as image:
        # A thin stroke must remain dark after the automatic preprocessing.
        assert image.getextrema()[0] < 80


def test_existing_nonuniform_background_contrast_input_is_retained_byte_for_byte():
    content = photo(gradient=True)
    box = (0, 0, 500, 240)
    old = prepare_material_region(content, box, rotated=True, enhancement='adaptive')
    new = prepare_material_region(content, box, rotated=True, enhancement='adaptive_mild')
    assert old.enhancement == new.enhancement == 'local_contrast'
    assert new.content == old.content
    assert new.transform == old.transform


@pytest.mark.parametrize('angle', [-6, 0, 6])
def test_new_automatic_contrast_never_changes_inverse_geometry(angle):
    content = photo()
    options = {'rotated': True, 'rotation_degrees': angle, 'font_height': 24}
    old = prepare_material_region(content, (100, 20, 400, 210), enhancement='standard', **options)
    new = prepare_material_region(content, (100, 20, 400, 210), enhancement='adaptive_mild', **options)
    assert old.transform == new.transform
    assert old.region == new.region
    with Image.open(BytesIO(old.content)) as old_image, Image.open(BytesIO(new.content)) as new_image:
        assert old_image.size == new_image.size


@pytest.mark.parametrize('text,expected', [
    ('혼용률 면50% 리에라의50%', True),
    ('혼용률 면50% 폴리에스터50%', False),
    ('혼용률 면49% 리에라의50%', False),
    ('혼용률 면100% 리에라의50%', False),
    ('혼용률 UNKNOWN50% 리에라의50%', False),
    ('OUTER COTTON50% UNKNOWN50%', False),
    ('혼용률 면50% 나일론25% 폴리에스터25%', False),
])
def test_mild_name_filter_is_selected_from_failed_ocr_evidence_only(text, expected):
    from apps.text import ocr_text
    assert ocr_text._prefer_mild_region_contrast([ocr_text._build_candidate('original', text)]) is expected


def test_name_filter_uses_existing_last_slot_and_keeps_request_budget(monkeypatch):
    from apps.text import ocr_text
    from apps.text.ocr_layout import OcrWord
    words = (OcrWord('혼용률', 120, 80, 180, 100), OcrWord('면', 190, 80, 210, 100),
             OcrWord('50%', 220, 80, 250, 100), OcrWord('리에라의', 260, 80, 330, 100),
             OcrWord('50%', 350, 80, 390, 100))
    options, calls = [], []
    def provider(_client, content, **kwargs):
        calls.append(content)
        return ocr_text.OcrPayload('혼용률 면50% 리에라의50%', layout_words=words)
    def prepare(content, box, **kwargs):
        options.append(kwargs['enhancement'])
        return prepare_material_region(content, box, **kwargs)
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *args: object())
    monkeypatch.setattr(ocr_text, '_resolve_credential_path', lambda *args: (None, None))
    monkeypatch.setattr(ocr_text, '_run_google_ocr', provider)
    monkeypatch.setattr(ocr_text, 'prepare_material_region', prepare)
    monkeypatch.setattr(ocr_text, 'find_material_region', lambda *_args: (100, 20, 400, 210))
    result = ocr_text.run_ocr_bytes(photo(), enable_reflection=False, enable_denoised=False,
                                  enable_rotated=False, enable_material_region=True)
    assert options == ['standard', 'mild_contrast']
    assert len(calls) == result.metadata.external_call_count == 4
    assert result.metadata.attempt_count == 4
